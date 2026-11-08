"""Specification tests for the workspace audit: small, hand-checkable repositories."""

import json
from datetime import date

import pytest
from conftest import DATA_DIR

from audit import checks
from audit.core import Finding, load_policy

POLICY = load_policy(DATA_DIR / "policy.json")

GOOD_AGENTS = """# Agent instructions

## Project overview
A thing.

## Commands
- Test: `python -m pytest -q`
- Lint: `python tools/lint.py`

## Architecture
src/

## Conventions
Small diffs.

## Boundaries
Never merge.
"""


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def ids(findings):
    return [f.check for f in findings]


# ------------------------------------------------------------ instructions

def test_missing_instructions_file_is_one_ws001(tmp_path):
    assert checks.check_instructions(tmp_path, POLICY) == [Finding("WS001", "AGENTS.md", None, "no agent instructions file")]


def test_complete_instructions_file_has_no_findings(tmp_path):
    write(tmp_path, "AGENTS.md", GOOD_AGENTS)
    assert checks.check_instructions(tmp_path, POLICY) == []


def test_claude_md_is_accepted_when_agents_md_is_absent(tmp_path):
    write(tmp_path, "CLAUDE.md", GOOD_AGENTS)
    assert checks.check_instructions(tmp_path, POLICY) == []


def test_missing_sections_are_reported_in_policy_order(tmp_path):
    text = GOOD_AGENTS.replace("## Architecture", "### Architecture").replace("## Boundaries", "Boundaries")
    write(tmp_path, "AGENTS.md", text)
    found = checks.check_instructions(tmp_path, POLICY)
    assert [(f.check, f.message) for f in found] == [
        ("WS002", "missing section 'Architecture'"), ("WS002", "missing section 'Boundaries'")]


def test_missing_lint_command_is_ws004_and_needs_a_value(tmp_path):
    write(tmp_path, "AGENTS.md", GOOD_AGENTS.replace("- Lint: `python tools/lint.py`", "- Lint:"))
    found = checks.check_instructions(tmp_path, POLICY)
    assert [(f.check, f.message) for f in found] == [("WS004", "no 'Lint' command")]


def test_commands_are_not_checked_when_the_section_is_missing(tmp_path):
    write(tmp_path, "AGENTS.md", GOOD_AGENTS.replace("## Commands", "## Scripts"))
    assert ids(checks.check_instructions(tmp_path, POLICY)) == ["WS002"]


def test_long_instructions_file_is_ws003(tmp_path):
    write(tmp_path, "AGENTS.md", GOOD_AGENTS + "- filler\n" * 140)
    found = checks.check_instructions(tmp_path, POLICY)
    assert [(f.check, f.message) for f in found] == [("WS003", "157 lines; policy maximum is 150")]


# ------------------------------------------------------------ secrets

TOKEN = "rly_live_" + "0123456789abcdef" * 2


def test_committed_env_file_and_each_secret_line(tmp_path):
    write(tmp_path, ".env", f"RELAY_API_TOKEN={TOKEN}\nREGION=eu-west-1\nDB_PASSWORD=hunter2hunter2\n")
    found = checks.scan_secrets(tmp_path, POLICY)
    assert [(f.check, f.line) for f in found] == [("WS011", None), ("WS010", 1), ("WS010", 3)]
    # The first matching pattern wins: one secret is one finding.
    assert found[1].message == "relay-token: rly_…"
    assert found[2].message == "env-assignment: DB_P…"


def test_findings_never_contain_the_secret(tmp_path):
    write(tmp_path, "notes.md", f"use postgresql://admin:s3cret-pass@db.internal/relay and {TOKEN}\n")
    found = checks.scan_secrets(tmp_path, POLICY)
    assert len(found) == 1 and found[0].message == "relay-token: rly_…"  # first pattern in policy order wins
    assert all("s3cret" not in f.message and TOKEN not in f.message for f in found)


def test_env_example_with_empty_values_is_allowed(tmp_path):
    write(tmp_path, ".env.example", "RELAY_API_TOKEN=\nRELAY_DB_PATH=data/relay-test.sql\n")
    write(tmp_path, "src/app.py", 'token = os.environ["RELAY_API_TOKEN"]\n')
    assert checks.scan_secrets(tmp_path, POLICY) == []


def test_skip_dirs_and_binary_files_are_not_scanned(tmp_path):
    write(tmp_path, "node_modules/pkg/x.js", f"const t = '{TOKEN}'\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\x00\x00" + TOKEN.encode())
    write(tmp_path, "id_ed25519", "not really a key\n")
    assert [(f.check, f.path) for f in checks.scan_secrets(tmp_path, POLICY)] == [("WS011", "id_ed25519")]


# ------------------------------------------------------------ sandbox

def devcontainer(tmp_path, **cfg):
    write(tmp_path, ".devcontainer/devcontainer.json", json.dumps(cfg))


def test_missing_devcontainer_is_ws020(tmp_path):
    assert ids(checks.check_sandbox(tmp_path, POLICY)) == ["WS020"]


def test_credential_mounts_in_both_forms(tmp_path):
    devcontainer(tmp_path, image="img@sha256:abc", mounts=[
        "source=${localEnv:HOME}/.aws,target=/home/vscode/.aws,type=bind",
        {"source": "/var/run/docker.sock", "target": "/var/run/docker.sock", "type": "bind"},
        "source=relay-cache,target=/cache,type=volume",
    ])
    found = checks.check_sandbox(tmp_path, POLICY)
    assert [f.message for f in found] == [
        "mount source '${localEnv:HOME}/.aws' exposes host credentials",
        "mount source '/var/run/docker.sock' exposes host credentials"]


def test_dangerous_run_args_and_privileged_flag(tmp_path):
    devcontainer(tmp_path, image="img@sha256:abc", privileged=True,
                 runArgs=["--network=host", "--networkx", "--cap-drop=ALL", "--privileged"])
    found = checks.check_sandbox(tmp_path, POLICY)
    assert [f.message for f in found] == ["run argument '--network=host'", "run argument '--privileged'",
                                          "privileged: true"]


def test_image_pinned_by_tag_is_low_ws023(tmp_path):
    devcontainer(tmp_path, image="mcr.microsoft.com/devcontainers/python:3.12")
    found = checks.check_sandbox(tmp_path, POLICY)
    assert ids(found) == ["WS023"] and found[0].severity == "low"


# ------------------------------------------------------------ branch protection

GOOD_BP = {
    "required_status_checks": {"strict": True, "contexts": ["tests", "secret-scan"]},
    "required_pull_request_reviews": {"required_approving_review_count": 1, "require_code_owner_reviews": True},
    "enforce_admins": {"enabled": True},
    "allow_force_pushes": {"enabled": False},
}


def test_compliant_branch_protection_has_no_findings(tmp_path):
    write(tmp_path, "governance/branch-protection.json", json.dumps(GOOD_BP))
    write(tmp_path, ".github/CODEOWNERS", "* @relay/maintainers\n")
    assert checks.check_branch_protection(tmp_path, POLICY) == []


def test_missing_export_and_codeowners(tmp_path):
    assert ids(checks.check_branch_protection(tmp_path, POLICY)) == ["WS030", "WS036"]


def test_every_branch_protection_gap(tmp_path):
    bp = {"required_status_checks": {"contexts": ["tests"]}, "required_pull_request_reviews": None,
          "enforce_admins": {"enabled": False}, "allow_force_pushes": {"enabled": True}}
    write(tmp_path, "governance/branch-protection.json", json.dumps(bp))
    write(tmp_path, "CODEOWNERS", "* @relay/maintainers\n")
    found = checks.check_branch_protection(tmp_path, POLICY)
    assert [(f.check, f.message) for f in found] == [
        ("WS031", "0 required; policy minimum is 1"),
        ("WS032", "code-owner review not required"),
        ("WS033", "status check 'secret-scan' not required"),
        ("WS034", "protection does not apply to administrators"),
        ("WS035", "force pushes to the protected branch are allowed"),
    ]


# ------------------------------------------------------------ MCP

def test_no_mcp_config_is_fine(tmp_path):
    assert checks.check_mcp(tmp_path, POLICY) == []


def test_mcp_allowlist_pins_the_command_not_just_the_name(tmp_path):
    pinned = POLICY["mcp"]["allowlist"]["relay-db-readonly"]
    write(tmp_path, ".mcp.json", json.dumps({"mcpServers": {
        "relay-db-readonly": {"command": "npx", "args": ["-y", "some-sql-server@latest"]},
        "aaa-search": {"command": "npx", "args": []},
    }}))
    found = checks.check_mcp(tmp_path, POLICY)
    assert [(f.check, f.message) for f in found] == [
        ("WS040", "server 'aaa-search' is not allowlisted"),
        ("WS041", "server 'relay-db-readonly' launch differs from the pinned command")]
    write(tmp_path, ".mcp.json", json.dumps({"mcpServers": {"relay-db-readonly": dict(pinned, env={"X": "1"})}}))
    assert checks.check_mcp(tmp_path, POLICY) == []


# ------------------------------------------------------------ waivers

LOW = Finding("WS023", ".devcontainer/devcontainer.json", None, "image pinned by tag")
CRIT = Finding("WS010", ".env", 1, "relay-token: rly_…")
WAIVER = {"check": "WS023", "path": ".devcontainer/devcontainer.json", "reason": "until Ch13",
          "owner": "sam.o", "expires": "2027-01-31"}


def test_valid_waiver_moves_a_low_finding_to_waived():
    assert checks.apply_waivers([CRIT, LOW], [WAIVER], POLICY, date(2027, 1, 31)) == ([CRIT], [LOW])


@pytest.mark.parametrize("change", [{"expires": "2027-01-30"}, {"owner": " "}, {"reason": ""},
                                    {"path": "other.json"}, {"check": "WS021"}])
def test_invalid_waivers_do_not_apply(change):
    assert checks.apply_waivers([LOW], [dict(WAIVER, **change)], POLICY, date(2027, 1, 31)) == ([LOW], [])


def test_critical_and_high_findings_can_never_be_waived():
    waiver = dict(WAIVER, check="WS010", path=".env")
    assert checks.apply_waivers([CRIT], [waiver], POLICY, date(2026, 11, 8)) == ([CRIT], [])

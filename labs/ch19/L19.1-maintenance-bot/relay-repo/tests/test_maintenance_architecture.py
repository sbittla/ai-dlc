"""relay.maintenance's boundaries and the bot's identity (4.31.0, ADR-053), read with `ast` and as text."""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "relay" / "maintenance"
NETWORK = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "asyncio", "ftplib", "xmlrpc"}
MODULES = ["__init__", "agent_step", "autonomy", "evidence", "guard", "longrun", "policy", "proposals", "reports",
           "safety_case", "semver", "tables", "updates"]


def imports(path):
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(("." * node.level) + (node.module or ""))
    return out


def test_the_package_has_its_modules_and_only_standard_library_or_relay_imports():
    assert sorted(p.stem for p in PACKAGE.glob("*.py")) == MODULES
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    assert [(p.name, m) for p in PACKAGE.glob("*.py") for m in imports(p)
            if not m.startswith(".") and m.split(".")[0] not in stdlib] == []


def test_no_network_module_no_process_start_and_no_merge_or_approve_function():
    names = [(p.name, m) for p in PACKAGE.glob("*.py") for m in imports(p)]
    assert [x for x in names if x[1].lstrip(".").split(".")[0] in NETWORK | {"subprocess"}] == []
    defs = {n.name for p in PACKAGE.glob("*.py") for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not {d for d in defs if d.startswith(("merge", "approve_", "deploy", "push"))}


def test_nothing_else_in_relay_imports_the_maintenance_package():
    users = [p for p in (ROOT / "src" / "relay").rglob("*.py") if PACKAGE not in p.parents
             and ("relay.maintenance" in p.read_text(encoding="utf-8") or "from ..maintenance" in
                  p.read_text(encoding="utf-8"))]
    assert users == []


def test_the_bot_has_its_own_identity_and_app_that_cannot_approve_merge_or_touch_workflows():
    data = json.loads((ROOT / "governance" / "agents.json").read_text(encoding="utf-8"))
    bot = next(a for a in data["agents"] if a["agent_id"] == "maintenance-bot")
    assert bot["kind"] == "ci-job" and bot["cloud_role"] is None and bot["delegation"] == "owner"
    assert bot["subject"] == "repo:relay-example/relay:environment:maintenance"
    assert not any(s.split(":")[1] in {"export", "admin", "write"} for s in bot["scopes"])
    app = data["github_apps"][bot["github_app"]]
    assert app["code_owner"] is False and app["bypass_branch_protection"] is False
    assert set(app["installation_permissions"]) == {"contents", "pull_requests", "metadata"}
    assert "workflows" not in app["installation_permissions"]
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "relay-maintenance" not in owners and "maintenance-bot" not in owners
    protection = json.loads((ROOT / "governance" / "branch-protection.json").read_text(encoding="utf-8"))
    assert protection["restrictions"]["apps"] == []


def test_the_policy_and_the_bot_are_owned_by_people_and_the_policy_owner_is_not_the_bot_owner():
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for line in ("/src/relay/maintenance/  @relay/security",
                 "/maintenance/       @relay/security @relay/platform-leads",
                 "/.github/workflows/maintenance.yml  @relay/platform-leads @relay/security",
                 "/tests/test_maintenance_*  @relay/security"):
        assert line in owners
    policy = json.loads((ROOT / "maintenance" / "policy.json").read_text(encoding="utf-8"))
    assert policy["owner"] != policy["bot_owner"]


def test_the_workflow_starts_only_on_a_schedule_or_by_hand_and_reads_the_policy_from_main():
    text = (ROOT / ".github" / "workflows" / "maintenance.yml").read_text(encoding="utf-8")
    head = text.split("\njobs:\n", 1)[0]
    triggers = [ln.strip().rstrip(":") for ln in head.split("\non:\n", 1)[1].splitlines()
                if ln.startswith("  ") and not ln.startswith("    ")]
    assert triggers == ["schedule", "workflow_dispatch"]
    assert "ref: main" in text and "environment: maintenance" in text and "persist-credentials: false" in text


def _guard_rules(path):
    """What Chapter 15's pipeline guard demands of a pull request touching `path`, from its policy file (the guard
    itself runs from the platform team's repository; this reads the same configuration)."""
    guard = json.loads((ROOT / "governance" / "pipeline-guard.json").read_text(encoding="utf-8"))
    under = lambda rules: any(path.startswith(r) if r.endswith(("/", "_")) else path == r for r in rules)  # noqa: E731
    rules = set()
    if under(guard["pipeline_paths"]):
        rules |= {"PG001 travels alone", "PG002 two approvals, one from the owner team"}
    if under(guard["gate_config_paths"]):
        rules.add("PG003 an approval from the weakening team")
    return rules


def test_the_pipeline_guard_covers_the_bots_policy_code_tests_and_workflow():
    for path in ("maintenance/policy.json", "maintenance/eligibility/docs-upkeep.json", "maintenance/dst-rules.json",
                 "src/relay/maintenance/policy.py", "tests/test_maintenance_policy.py", "tests/maintenance_helpers.py",
                 ".github/workflows/maintenance.yml", "governance/agents.json"):
        assert "PG002 two approvals, one from the owner team" in _guard_rules(path), path
    # A T4 grant is a change to the policy and its report: two approvals and a security approval.
    assert _guard_rules("maintenance/policy.json") == {"PG001 travels alone",
                                                       "PG002 two approvals, one from the owner team",
                                                       "PG003 an approval from the weakening team"}

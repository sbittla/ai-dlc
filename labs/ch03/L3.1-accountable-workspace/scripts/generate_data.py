"""Write Lab 3.1's policy and its two repository snapshots into data/.

    python scripts/generate_data.py

data/policy.json        the accountable-workspace policy the audit enforces
data/repos/before/      Relay's workspace on the day of the Chapter 3 incident
data/repos/after/       the same workspace after this chapter's hardening

"after" is a copy of solution/relay-repo. "before" uses the same code with the
unfixed due-date module (tests/fixtures/buggy_duedates.py), without the RLY-412
regression test, and with the workspace configuration the team had at the time.

All secrets in "before" are fake. The AWS values are the placeholder keys from
AWS's own documentation; the Relay token is derived from a fixed seed. Real
secret scanners may still flag them, which is the point.
Output is byte-identical on every platform (LF line endings, sorted order).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
DATA = LAB / "data"
SOURCE = LAB / "solution" / "relay-repo"
SKIP = {"__pycache__", ".pytest_cache", ".venv"}

POLICY = {
    "policy_version": "workspace-policy-v1",
    "instructions": {
        "files": ["AGENTS.md", "CLAUDE.md"],
        "required_sections": ["Project overview", "Commands", "Architecture", "Conventions", "Boundaries"],
        "commands_section": "Commands",
        "required_commands": ["Test", "Lint"],
        "max_lines": 150,
    },
    "secrets": {
        "patterns": [
            {"id": "private-key", "regex": r"-----BEGIN [A-Z ]*PRIVATE KEY-----"},
            {"id": "aws-access-key-id", "regex": r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"},
            {"id": "relay-token", "regex": r"\brly_(live|test)_[0-9a-f]{32}\b"},
            {"id": "github-token", "regex": r"\bgh[pousr]_[A-Za-z0-9]{36}\b"},
            {"id": "url-credentials", "regex": r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"]+:[^/\s@'\"]+@"},
            {"id": "env-assignment",
             "regex": r"^\s*(export\s+)?[A-Z0-9_]*(PASSWORD|SECRET|API_KEY|TOKEN)[A-Z0-9_]*\s*=\s*[^\s$#'\"]{8,}"},
        ],
        "forbidden_files": [".env", ".env.*", "*.pem", "*.key", "*.p12", "id_rsa*", "id_ed25519*", ".netrc"],
        "allowed_files": [".env.example"],
        "skip_dirs": [".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"],
    },
    "sandbox": {
        "file": ".devcontainer/devcontainer.json",
        "forbidden_mount_fragments": [".aws", ".ssh", ".config/gcloud", ".azure", ".kube", ".docker",
                                      "docker.sock", ".gnupg", ".netrc"],
        "forbidden_run_args": ["--privileged", "--network", "--pid", "--ipc", "--cap-add"],
        "require_image_digest": True,
    },
    "branch_protection": {
        "file": "governance/branch-protection.json",
        "codeowners": [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"],
        "min_approving_reviews": 1,
        "require_code_owner_reviews": True,
        "required_status_checks": ["tests", "secret-scan"],
        "enforce_admins": True,
        "allow_force_pushes": False,
    },
    "mcp": {
        "file": ".mcp.json",
        "allowlist": {
            "relay-db-readonly": {"command": "python",
                                  "args": ["-m", "relaymcp.server", "--db", "data/relay-test.sql"]},
        },
    },
    "waivers": {"file": "governance/waivers.json", "waivable_severities": ["low", "medium"]},
}

TEST_DB_URL = "postgresql://relay_admin:Tr0ub4dor-staging@test-db.relay.internal:5432/relay_test"
SPRINT_TOPICS = [
    "moved the export job to the background queue",
    "renamed the Projects tab to Workspaces, then back",
    "webhook retries now back off exponentially (8 attempts)",
    "agreed to stop using the shared staging login",
    "flaky store test traced to test ordering",
    "SSO session default is 12 hours",
    "Guests must not see the member directory",
    "we tried the new lint rules and turned half of them off",
]


def before_agents_md() -> str:
    lines = [
        "# Relay agent notes",
        "",
        "## Project overview",
        "",
        "Relay is our task and workflow platform. Python, standard library only.",
        "",
        "## Commands",
        "",
        "- Test: `python -m pytest -q`",
        "",
        "## Conventions",
        "",
        "- Keep changes small and run the tests.",
        "- For anything involving real-looking data, use the shared test database:",
        f"  {TEST_DB_URL}",
        "- The cloud profile relay-dev-admin is already configured in the dev container.",
        "- You can clean up test data yourself; nobody else uses the test database at night.",
        "",
        "## Notes",
        "",
        "Pasted from the team wiki so the agent has context.",
        "",
    ]
    for sprint in range(1, 25):
        for k in range(8):
            if (sprint + k) % 4 != 0:
                lines.append(f"- Sprint {sprint}: {SPRINT_TOPICS[(sprint * 3 + k) % len(SPRINT_TOPICS)]}.")
    return "\n".join(lines) + "\n"


def relay_token(seed: str) -> str:
    return "rly_live_" + hashlib.sha256(seed.encode()).hexdigest()[:32]


BEFORE_FILES = {
    "AGENTS.md": before_agents_md(),
    ".env": "\n".join([
        f"RELAY_API_TOKEN={relay_token('lab-3.1-before')}",
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "AWS_DEFAULT_REGION=eu-west-1",
    ]) + "\n",
    ".gitignore": "__pycache__/\n.pytest_cache/\n",
    ".devcontainer/devcontainer.json": json.dumps({
        "name": "relay-dev",
        "image": "mcr.microsoft.com/devcontainers/python:3.12",
        "runArgs": ["--privileged"],
        "mounts": [
            "source=${localEnv:HOME}/.aws,target=/home/vscode/.aws,type=bind",
            "source=${localEnv:HOME}/.ssh,target=/home/vscode/.ssh,type=bind,readonly",
        ],
        "remoteEnv": {"AWS_PROFILE": "relay-dev-admin"},
        "postCreateCommand": "python -m pip install --user pytest==9.1.1",
    }, indent=2) + "\n",
    ".mcp.json": json.dumps({"mcpServers": {
        "relay-db-readonly": {"command": "npx", "args": ["-y", "@example/sql-mcp@latest", "--allow-writes"],
                              "env": {"DATABASE_URL": TEST_DB_URL}},
        "web-fetch": {"command": "npx", "args": ["-y", "@example/fetch-mcp@latest"]},
    }}, indent=2) + "\n",
    "governance/branch-protection.json": json.dumps({
        "branch": "main",
        "required_status_checks": None,
        "required_pull_request_reviews": {"required_approving_review_count": 0,
                                          "require_code_owner_reviews": False, "dismiss_stale_reviews": False},
        "enforce_admins": {"enabled": False},
        "allow_force_pushes": {"enabled": True},
        "allow_deletions": {"enabled": False},
    }, indent=2) + "\n",
}
# Files in solution/relay-repo that the "before" workspace did not have yet.
BEFORE_OMITS = {".env.example", ".github/CODEOWNERS", "governance/waivers.json", "tests/test_due_dates_rly412.py",
                "AGENTS.md", ".gitignore", ".devcontainer/devcontainer.json", ".mcp.json",
                "governance/branch-protection.json"}


def lf(text: str) -> bytes:
    return text.replace("\r\n", "\n").encode("utf-8")


def source_files() -> dict[str, bytes]:
    out = {}
    for path in sorted(SOURCE.rglob("*")):
        if path.is_file() and not (set(path.relative_to(SOURCE).parts) & SKIP) and path.suffix != ".pyc":
            out[path.relative_to(SOURCE).as_posix()] = lf(path.read_text(encoding="utf-8"))
    return out


def write_tree(root: Path, files: dict[str, bytes]) -> None:
    if root.exists():
        shutil.rmtree(root)
    for name in sorted(files):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[name])


def main() -> None:
    DATA.mkdir(exist_ok=True)
    (DATA / "policy.json").write_bytes(lf(json.dumps(POLICY, indent=2) + "\n"))
    after = source_files()
    before = {k: v for k, v in after.items() if k not in BEFORE_OMITS}
    before["src/relay/duedates.py"] = lf((LAB / "tests" / "fixtures" / "buggy_duedates.py").read_text(encoding="utf-8"))
    before.update({k: lf(v) for k, v in BEFORE_FILES.items()})
    write_tree(DATA / "repos" / "before", before)
    write_tree(DATA / "repos" / "after", after)
    print(f"wrote data/policy.json, repos/before ({len(before)} files), repos/after ({len(after)} files)")


if __name__ == "__main__":
    main()

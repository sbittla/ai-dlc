"""Build the canonical Relay 4.23.0 from the two Batch 4 branches.

Chapter 9 (Relay 4.22.0) changed escalation, worker and service code: rule
deletion (spec 1.2.0), escalation passes in the worker, the modernized
`relay/notify/` module, ADR-016 to ADR-019. Chapter 14 (its own 4.23.0) added
agent identities, the audit trail and the kill switch: `relay/audit/`,
`governance/agents.json`, `infra/agents.tf`, `infra/detection/`, runbooks and
ADR-020 to ADR-023. Both started from canonical 4.21.0. This script takes
Chapter 9 as the base and applies Chapter 14's changes deterministically:

    python labs/relay-baselines/merge_4_23_0.py

Output: labs/relay-baselines/4.23.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
BASE = LABS / "relay-baselines/4.21.0/relay-repo"
CH9 = LABS / "ch09/L9.1-spec-to-reviewed-pr/solution/relay-repo"
CH14 = LABS / "ch14/L14.1-agent-identity-kill-switch/relay-repo"
OUT = LABS / "relay-baselines/4.23.0/relay-repo"
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*")

CH14_DIRS = ["src/relay/audit", "infra/detection"]
CH14_FILES = [
    "governance/agents.json",
    "infra/agents.tf",
    "infra/runbooks/ai-incident-playbook.md",
    "infra/runbooks/break-glass.md",
    "infra/runbooks/kill-switch.md",
    "docs/adr/ADR-020-agent-identity-short-lived-tokens.md",
    "docs/adr/ADR-021-audit-trail-of-agent-actions.md",
    "docs/adr/ADR-022-detection-rules-and-kill-switch.md",
    "docs/adr/ADR-023-privacy-for-prompts-logs-and-traces.md",
    "tests/test_audit_architecture.py",
    "tests/test_audit_identity.py",
    "tests/test_audit_killswitch.py",
    "tests/test_audit_redact.py",
    "tests/test_audit_registry_file.py",
    "tests/test_audit_trail.py",
    "tests/test_infra_agent_identity.py",
]
# Changed by Chapter 14 only: Chapter 9 must still have 4.21.0's copy.
CH14_ONLY_MODIFIED = [
    "infra/iam.tf",
    "infra/runbooks/bootstrap.md",
    "governance/branch-protection.json",
]
VERSION_EDITS = {
    "pyproject.toml": ('version = "4.22.0"', 'version = "4.23.0"'),
    "src/relay/__init__.py": ('__version__ = "4.22.0"', '__version__ = "4.23.0"'),
    "tests/test_service_app.py": ('__version__ == "4.22.0"', '__version__ == "4.23.0"'),
    "tests/test_service_http.py": ('[1]["version"] == "4.22.0"', '[1]["version"] == "4.23.0"'),
    "tests/test_service_wsgi.py": ('body["version"] == "4.22.0"', 'body["version"] == "4.23.0"'),
}


def read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"anchor not found exactly once: {old!r}")
    return text.replace(old, new)


def main() -> None:
    for source in (BASE, CH9, CH14):
        if not source.is_dir():
            raise SystemExit(f"missing tree: {source}")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH9, OUT, ignore=IGNORE)

    for name in CH14_DIRS:
        if (OUT / name).exists():
            raise SystemExit(f"Chapter 14 folder already exists in Chapter 9's tree: {name}")
        shutil.copytree(CH14 / name, OUT / name, ignore=IGNORE)
    for name in CH14_FILES:
        if (OUT / name).exists():
            raise SystemExit(f"Chapter 14 file already exists in Chapter 9's tree: {name}")
        (OUT / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CH14 / name, OUT / name)
    for name in CH14_ONLY_MODIFIED:
        if not filecmp.cmp(BASE / name, CH9 / name, shallow=False):
            raise SystemExit(f"both branches changed {name}; merge it by hand")
        shutil.copyfile(CH14 / name, OUT / name)

    for name, (old, new) in VERSION_EDITS.items():
        text, nl = read(OUT / name)
        write(OUT / name, replace_once(text, old, new), nl)

    agents, nl = read(OUT / "AGENTS.md")
    agents = replace_once(
        agents,
        "passes in the worker and the notification preferences module (4.22.0).\n",
        "passes in the worker and the notification preferences module (4.22.0),\n"
        "and agent identities, the audit trail of agent actions and the kill switch (4.23.0).\n",
    )
    agents = replace_once(
        agents,
        "- `specs/`: approved specifications.",
        "- `src/relay/audit/`: agent identities and 15-minute tokens, the hash-chained audit trail, redaction and the\n"
        "  kill switch (ADR-020 to ADR-023). `governance/agents.json` registers every agent; `infra/agents.tf` its roles.\n"
        "- `specs/`: approved specifications.",
    )
    no_deps = "- Do not add dependencies. If you think one is needed, stop and say why.\n"
    agents = replace_once(
        agents,
        no_deps,
        no_deps + "- Never log a token, a request header or a request body. Pass anything bound for a log through"
        " `relay.audit.redact`.\n",
    )
    last = "- If a test fails for a reason you do not understand, stop and explain; do not delete or skip it.\n"
    agents = replace_once(
        agents,
        last,
        "- You act under your own agent identity with 15-minute tokens. Never copy, print or store a token, never ask\n"
        "  for a scope the task does not need, and never edit `governance/agents.json`, `infra/agents.tf` or"
        " `infra/detection/`.\n" + last,
    )
    write(OUT / "AGENTS.md", agents, nl)

    owners, nl = read(OUT / ".github/CODEOWNERS")
    ch14_lines = [line for line in read(CH14 / ".github/CODEOWNERS")[0].splitlines()
                  if line.startswith(("/src/relay/audit/", "/governance/agents.json", "/infra/agents.tf",
                                      "/infra/detection/"))]
    if len(ch14_lines) != 4:
        raise SystemExit(f"expected 4 Chapter 14 CODEOWNERS lines, found {len(ch14_lines)}")
    owners = owners.rstrip("\n") + "\n" + "\n".join(ch14_lines) + "\n"
    write(OUT / ".github/CODEOWNERS", owners, nl)

    print(f"wrote canonical Relay 4.23.0 to {OUT}")


if __name__ == "__main__":
    main()

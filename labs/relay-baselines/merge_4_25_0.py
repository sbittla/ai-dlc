"""Build the canonical Relay 4.25.0 from the two Batch 5 branches.

Chapter 10 (Relay 4.24.0) added the agent runtime `relay/agents/` (budgets,
tool contracts and the tool-call boundary, resumable runs, approval gates,
reviewed memory), the spec-to-PR helper's registry entry and ADR-024 to
ADR-027. Chapter 13 (its own 4.25.0) added the supply-chain controls, security
gates, SBOM and AI-BOM, the deployment wiring and ADR-028 to ADR-031, and
changed deploy, infra, CI and service files. Both started from canonical
4.23.0. Chapter 10 added files almost only, so this script takes Chapter 13's
tree as the base and applies Chapter 10's changes deterministically:

    python labs/relay-baselines/merge_4_25_0.py

Output: labs/relay-baselines/4.25.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
BASE = LABS / "relay-baselines/4.23.0/relay-repo"
CH10 = LABS / "ch10/L10.1-workflow-agent-multiagent/solution/relay-repo"
CH13 = LABS / "ch13/L13.1-secure-agent-loop/relay-repo"
OUT = LABS / "relay-baselines/4.25.0/relay-repo"
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*")

CH10_DIRS = ["src/relay/agents"]
CH10_FILES = [
    "docs/adr/ADR-024-agent-loop-budgets-and-stopping.md",
    "docs/adr/ADR-025-tool-contracts-and-boundary.md",
    "docs/adr/ADR-026-run-state-idempotency-and-approval.md",
    "docs/adr/ADR-027-spec-to-pr-helper-design.md",
    "tests/agents_helpers.py",
    "tests/test_agents_approval.py",
    "tests/test_agents_architecture.py",
    "tests/test_agents_boundary.py",
    "tests/test_agents_budget.py",
    "tests/test_agents_contracts.py",
    "tests/test_agents_loop.py",
    "tests/test_agents_memory.py",
    "tests/test_agents_state.py",
]
# Changed by Chapter 10 only: Chapter 13 must still have 4.23.0's copy.
CH10_ONLY_MODIFIED = ["governance/agents.json", "tests/test_audit_registry_file.py"]
# Changed by both branches, but by Chapter 10 only in its version string, which Chapter 13's 4.25.0 supersedes.
VERSION_ONLY_IN_CH10 = {
    "pyproject.toml": ('version = "4.23.0"', 'version = "4.24.0"'),
    "src/relay/__init__.py": ('__version__ = "4.23.0"', '__version__ = "4.24.0"'),
    "tests/test_service_app.py": ('== "4.23.0"', '== "4.24.0"'),
    "tests/test_service_http.py": ('== "4.23.0"', '== "4.24.0"'),
    "tests/test_service_wsgi.py": ('== "4.23.0"', '== "4.24.0"'),
}
CH10_CODEOWNERS = ("/src/relay/agents/", "/tests/test_agents_boundary.py", "/tests/test_agents_approval.py")


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
    for source in (BASE, CH10, CH13):
        if not source.is_dir():
            raise SystemExit(f"missing tree: {source}")
    for name, (old, new) in VERSION_ONLY_IN_CH10.items():
        if read(BASE / name)[0].replace(old, new) != read(CH10 / name)[0]:
            raise SystemExit(f"Chapter 10 changed more than the version in {name}; merge it by hand")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH13, OUT, ignore=IGNORE)

    for name in CH10_DIRS:
        if (OUT / name).exists():
            raise SystemExit(f"Chapter 10 folder already exists in Chapter 13's tree: {name}")
        shutil.copytree(CH10 / name, OUT / name, ignore=IGNORE)
    for name in CH10_FILES:
        if (OUT / name).exists():
            raise SystemExit(f"Chapter 10 file already exists in Chapter 13's tree: {name}")
        shutil.copyfile(CH10 / name, OUT / name)
    for name in CH10_ONLY_MODIFIED:
        if not filecmp.cmp(BASE / name, CH13 / name, shallow=False):
            raise SystemExit(f"both branches changed {name}; merge it by hand")
        shutil.copyfile(CH10 / name, OUT / name)

    agents, nl = read(OUT / "AGENTS.md")
    agents = replace_once(
        agents,
        "agent identities, the audit trail of agent actions and the kill switch (4.23.0),\n"
        "and supply-chain controls, security gates, signed SBOMs and the deployment wiring (4.25.0).\n",
        "agent identities, the audit trail of agent actions and the kill switch (4.23.0), the agent runtime:\n"
        "budgets, tool contracts, resumable runs and approval gates (4.24.0), and supply-chain controls,\n"
        "security gates, signed SBOMs and the deployment wiring (4.25.0).\n",
    )
    audit_line = ("  kill switch (ADR-020 to ADR-023). `governance/agents.json` registers every agent;"
                  " `infra/agents.tf` its roles.\n")
    agents = replace_once(
        agents,
        audit_line,
        audit_line
        + "- `src/relay/agents/`: the agent runtime (ADR-024 to ADR-027): budgets and stopping conditions, typed tool\n"
        "  contracts and the tool-call boundary, resumable run state, approval gates, compaction and reviewed memory.\n"
        "  The spec-to-PR helper runs on it.\n",
    )
    redact = ("- Never log a token, a request header or a request body. Pass anything bound for a log through"
              " `relay.audit.redact`.\n")
    agents = replace_once(
        agents,
        redact,
        redact
        + "- Every agent that changes code runs behind `relay.agents.ToolBoundary` under its own identity, with a budget\n"
        "  set from dev runs (ADR-024). A budget is raised only by a person other than the one who asked for the run.\n",
    )
    last = "- If a test fails for a reason you do not understand, stop and explain; do not delete or skip it.\n"
    agents = replace_once(
        agents,
        last,
        last
        + "- If a stop rule, a budget or an approval gate stops you, hand the task back with the reason. Never retry past\n"
        "  it, and never ask for an approval in other words.\n",
    )
    write(OUT / "AGENTS.md", agents, nl)

    # Integration edit: Chapter 13's AI-BOM lists every registered agent, and Chapter 10 registered one more.
    sbom_test, nl = read(OUT / "tests/test_sbom.py")
    sbom_test = replace_once(
        sbom_test,
        '                               "eval-harvester", "triage-worker"]}',
        '                               "eval-harvester", "spec-to-pr-helper", "triage-worker"]}',
    )
    write(OUT / "tests/test_sbom.py", sbom_test, nl)

    owners, nl = read(OUT / ".github/CODEOWNERS")
    ch10_lines = [line for line in read(CH10 / ".github/CODEOWNERS")[0].splitlines()
                  if line.startswith(CH10_CODEOWNERS)]
    if len(ch10_lines) != len(CH10_CODEOWNERS):
        raise SystemExit(f"expected {len(CH10_CODEOWNERS)} Chapter 10 CODEOWNERS lines, found {len(ch10_lines)}")
    owners = owners.rstrip("\n") + "\n" + "\n".join(ch10_lines) + "\n"
    write(OUT / ".github/CODEOWNERS", owners, nl)

    print(f"wrote canonical Relay 4.25.0 to {OUT}")


if __name__ == "__main__":
    main()

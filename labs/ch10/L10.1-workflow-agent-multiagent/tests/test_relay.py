"""Relay 4.24.0 in <target>/relay-repo: its own suite passes, and it changes only what Chapter 10 owns."""

import filecmp
import subprocess
import sys

from conftest import BASELINE, RELAY_REPO

ADDED_SRC = {f"src/relay/agents/{m}.py" for m in ("__init__", "approval", "boundary", "budget", "contracts", "loop",
                                                  "memory", "session", "state", "tools")}
ADDED_TESTS = {f"tests/{n}.py" for n in ("agents_helpers", "test_agents_approval", "test_agents_architecture",
                                         "test_agents_boundary", "test_agents_budget", "test_agents_contracts",
                                         "test_agents_loop", "test_agents_memory",
                                         "test_agents_state")}
ADDED_DOCS = {"docs/adr/ADR-024-agent-loop-budgets-and-stopping.md", "docs/adr/ADR-025-tool-contracts-and-boundary.md",
              "docs/adr/ADR-026-run-state-idempotency-and-approval.md", "docs/adr/ADR-027-spec-to-pr-helper-design.md"}
MODIFIED = {"pyproject.toml", "src/relay/__init__.py", "tests/test_service_app.py", "tests/test_service_http.py",
            "tests/test_service_wsgi.py", "tests/test_audit_registry_file.py", "governance/agents.json", "AGENTS.md",
            ".github/CODEOWNERS"}


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def test_only_chapter_10_files_are_added_or_changed():
    base, mine = files(BASELINE), files(RELAY_REPO)
    assert mine - base == ADDED_SRC | ADDED_TESTS | ADDED_DOCS
    assert base - mine == set()
    changed = {p for p in base & mine if not filecmp.cmp(BASELINE / p, RELAY_REPO / p, shallow=False)}
    assert changed == MODIFIED


def test_no_service_worker_escalation_audit_infra_or_deploy_change():
    for p in files(RELAY_REPO):
        if p.startswith(("src/relay/service/", "src/relay/worker/", "src/relay/escalation/", "src/relay/audit/",
                         "infra/", "deploy/", ".devcontainer/")):
            assert filecmp.cmp(BASELINE / p, RELAY_REPO / p, shallow=False), p


def test_relay_suite_passes():
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY_REPO,
                         capture_output=True, text=True)
    if run.returncode != 0 and "NotImplementedError: TODO" in run.stdout:
        raise NotImplementedError("Relay's suite stops on TODO 1 or 2 (relay.agents.budget, relay.agents.loop)")
    assert run.returncode == 0, run.stdout[-3000:]
    assert run.stdout.splitlines()[-1].startswith("562 passed")  # 473 from canonical 4.23.0 and 89 new

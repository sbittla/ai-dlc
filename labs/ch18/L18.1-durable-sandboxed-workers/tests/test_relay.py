"""Relay 4.30.0 in relay-repo/ is complete, changes only what Chapter 18 declares, and passes its own checks;
the generated data reproduces byte for byte."""

import os
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.28.0" / "relay-repo"
ADDED = {
    "docs/adr/ADR-049-agent-jobs-dead-letters-and-the-effect-ledger.md",
    "docs/adr/ADR-050-sandbox-for-agent-written-code.md",
    "docs/adr/ADR-051-shared-registry-state-and-the-agent-gateway.md",
    "docs/adr/ADR-052-model-hosting-managed-api-and-model-intake.md",
    "src/relay/agentops/__init__.py", "src/relay/agentops/effects.py", "src/relay/agentops/gateway.py",
    "src/relay/agentops/jobs.py", "src/relay/agentops/registry_state.py", "src/relay/agentops/resilience.py",
    "src/relay/agentops/sandbox.py", "src/relay/agentops/sandbox_child.py", "src/relay/agentops/tools.py",
    "src/relay/agentops/worker.py",
    "tests/agentops_helpers.py", "tests/test_agentops_architecture.py", "tests/test_agentops_effects_resilience.py",
    "tests/test_agentops_jobs.py", "tests/test_agentops_registry_gateway.py", "tests/test_agentops_sandbox.py",
    "tests/test_agentops_worker.py",
}
MODIFIED = {
    ".github/CODEOWNERS", "AGENTS.md", "pyproject.toml", "src/relay/__init__.py", "src/relay/service/monitor.py",
    "src/relay/service/wsgi.py", "tests/test_agents_architecture.py", "tests/test_service_app.py",
    "tests/test_telemetry_signals.py",
    "tests/test_service_http.py", "tests/test_service_wsgi.py",
}
SUITE = 981  # one platform-specific sandbox test is skipped on each platform: 980 passed, 1 skipped
GENERATED = {"manifest.json", "pilot/tickets.jsonl", "pilot/deliveries.jsonl", "escapes.json", "drills.json"}


def same(a, b) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == GENERATED
    for rel in GENERATED:
        assert (tmp_path / rel).read_bytes() == (DATA_DIR / rel).read_bytes().replace(b"\r\n", b"\n"), rel


def test_version_is_4_30_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.30.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.30.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_28_0():
    if not CANONICAL.is_dir():  # the lab copied out of the book's repository
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    assert ours - theirs == ADDED
    assert theirs - ours == set()
    changed = {f for f in ours & theirs if not same(RELAY / f, CANONICAL / f)}
    assert changed == MODIFIED
    untouched = ("src/relay/worker/", "src/relay/agents/", "src/relay/escalation/", "src/relay/audit/",
                 "src/relay/telemetry/", "src/relay/routing/", "infra/", "deploy/", "governance/", "supply-chain/",
                 "security/")
    assert not any(f.startswith(untouched) for f in changed | ADDED)


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    env["PYTHONPATH"] = str(RELAY / "src")
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=900, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    passed = int(re.search(r"\b(\d+) passed\b", out.stdout).group(1))
    skipped = re.search(r"\b(\d+) skipped\b", out.stdout)
    assert passed + (int(skipped.group(1)) if skipped else 0) == SUITE, out.stdout[-500:]


def test_relay_lint_and_supply_chain_check_are_clean():
    for cmd in (["tools/lint.py"], ["tools/supplychain.py"]):
        out = subprocess.run([sys.executable, *cmd], cwd=RELAY, capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout[-1000:]

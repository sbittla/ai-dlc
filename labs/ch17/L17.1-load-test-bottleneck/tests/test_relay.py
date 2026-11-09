"""Relay 4.28.0 in relay-repo/ is complete, changes only what Chapter 17 owns, and passes its own checks;
the generated data reproduces byte for byte."""

import json
import os
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.25.0" / "relay-repo"
ADDED = {
    "docs/adr/ADR-040-workload-model-load-test-and-performance-budgets.md",
    "docs/adr/ADR-041-shared-limiter-leases-blocks-of-counts.md",
    "docs/adr/ADR-042-triage-routing-token-limits-and-cost-per-success.md",
    "docs/adr/ADR-043-spend-quotas-and-spend-monitoring.md",
    "perf/budgets.json", "perf/workload.json",
    "src/relay/routing/__init__.py", "src/relay/routing/costs.py", "src/relay/routing/policy.py",
    "src/relay/routing/quota.py", "tests/routing_hooks.py", "tests/test_loadtest.py",
    "tests/test_routing_architecture.py", "tests/test_routing_costs.py", "tests/test_routing_hooks.py",
    "tests/test_routing_policy.py", "tests/test_routing_quota.py", "tools/loadtest.py",
}
MODIFIED = {
    ".github/CODEOWNERS", "AGENTS.md", "pyproject.toml", "src/relay/__init__.py", "src/relay/service/sharedlimit.py",
    "tests/test_service_app.py", "tests/test_service_http.py", "tests/test_service_sharedlimit.py",
    "tests/test_service_wsgi.py",
}
SUITE = 657
GENERATED = {"manifest.json", "traffic/meta.json", "traffic/week-2027-02-01.csv"}


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
        assert (tmp_path / rel).read_bytes() == (DATA_DIR / rel).read_bytes(), rel


def test_measured_runs_say_where_they_were_recorded():
    for name in ("steady-140.json", "stress-280.json", "stress-420.json", "stress-560.json"):
        data = json.loads((DATA_DIR / "measured" / name).read_text(encoding="utf-8"))
        assert {"platform", "cpus", "python", "sqlite"} <= set(data["environment"])
        assert data["tool"] == "relay tools/loadtest.py 4.28.0" and data["workload"] == "relay-api-weekday-peak"


def test_version_is_4_28_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.28.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.28.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_25_0():
    if not CANONICAL.is_dir():  # the lab copied out of the book's repository
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    assert ours - theirs == ADDED
    assert theirs - ours == set()
    changed = {f for f in ours & theirs if not same(RELAY / f, CANONICAL / f)}
    assert changed == MODIFIED
    owned_elsewhere = ("src/relay/worker/", "src/relay/agents/", "src/relay/escalation/", "src/relay/audit/",
                       "infra/", "deploy/", "governance/")
    assert not any(f.startswith(owned_elsewhere) for f in changed | ADDED)
    assert {f for f in changed if f.startswith("src/relay/service/")} == {"src/relay/service/sharedlimit.py"}


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    env["PYTHONPATH"] = str(RELAY / "src")
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=900, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(rf"\b{SUITE} passed\b", out.stdout), out.stdout[-500:]


def test_relay_lint_and_supply_chain_check_are_clean():
    for cmd in (["tools/lint.py"], ["tools/supplychain.py"]):
        out = subprocess.run([sys.executable, *cmd], cwd=RELAY, capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout[-1000:]

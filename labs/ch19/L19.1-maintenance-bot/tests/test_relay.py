"""Relay 4.31.0 in relay-repo/ is complete, changes only what Chapter 19 declares, and passes its own checks;
the generated data reproduces byte for byte."""

import os
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.30.0" / "relay-repo"
MODULES = ["__init__", "agent_step", "autonomy", "evidence", "guard", "longrun", "policy", "proposals", "reports",
           "safety_case", "semver", "tables", "updates"]
ADDED = {
    ".github/workflows/maintenance.yml", "maintenance/policy.json", "maintenance/dst-rules.json",
    "docs/adr/ADR-053-maintenance-bot-design.md", "docs/adr/ADR-054-dependency-and-vulnerability-updates.md",
    "docs/adr/ADR-055-long-running-maintenance-campaigns.md",
    "docs/adr/ADR-056-governing-autonomy-self-modification-and-safety-cases.md",
    *{f"src/relay/maintenance/{m}.py" for m in MODULES},
    "tests/maintenance_helpers.py", "tests/test_maintenance_agent_step.py", "tests/test_maintenance_architecture.py",
    "tests/test_maintenance_evidence.py", "tests/test_maintenance_governance.py", "tests/test_maintenance_longrun.py",
    "tests/test_maintenance_policy.py", "tests/test_maintenance_proposals.py", "tests/test_maintenance_updates.py",
}
MODIFIED = {
    ".github/CODEOWNERS", "AGENTS.md", "pyproject.toml", "src/relay/__init__.py", "governance/agents.json",
    "deploy/gitops/production.json", "governance/pipeline-guard.json",
    "tests/test_service_app.py", "tests/test_service_http.py",
    "tests/test_service_wsgi.py", "tests/test_audit_registry_file.py", "tests/test_agentops_architecture.py",
    "tests/test_agents_architecture.py", "tests/test_sbom.py",
}
SUITE = 1184  # one platform-specific sandbox test is skipped on each platform
GENERATED = {"manifest.json", "mirror.json", "incident-2027-05-20.json", "canary-2027-06-29.json", "history.json",
             "outcomes.json", "reports.json", "evidence.json", "webapp/signin.py", "webapp/app_tests.py",
             "webapp/round_trip.py", "webapp/repro_adv_0113.py", "webapp/CODEOWNERS", "webapp/pinned-defaults.json",
             "webapp/requirements-2.4.1.lock",
             *{f"packages/sessionkeel-{v}.py" for v in ("2.4.1", "2.4.2", "2.4.3", "2.5.0", "2.5.1", "3.0.0")}}


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


def test_version_is_4_31_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.31.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.31.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_30_0():
    if not CANONICAL.is_dir():  # the lab copied out of the book's repository
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    assert ours - theirs == ADDED
    assert theirs - ours == set()
    changed = {f for f in ours & theirs if not same(RELAY / f, CANONICAL / f)}
    assert changed == MODIFIED
    untouched = ("src/relay/service/", "src/relay/agents/", "src/relay/agentops/", "src/relay/audit/",
                 "src/relay/escalation/", "infra/", "docs/slo/", "supply-chain/", "security/", "deploy/admission/",
                 "deploy/rollout/")
    assert not any(f.startswith(untouched) for f in changed | ADDED)
    gov = {f for f in changed | ADDED if f.startswith("governance/")}
    assert gov == {"governance/agents.json", "governance/pipeline-guard.json"}


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

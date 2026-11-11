"""The generated data reproduces byte for byte, the vendored Lab 12.1 code is an exact copy, and Relay 4.29.0 in
relay-repo/ is complete and passes its suite, lint, the supply-chain check and the test-sandbox check.

4.29.0 starts from canonical 4.28.0. The sets below are the exact files it adds and modifies.
"""

import json
import os
import re
import subprocess
import sys

from conftest import CANONICAL, DATA_DIR, LAB_12_1, LAB_ROOT, RELAY

ADDED = {
    ".github/workflows/deploy.yml", ".github/workflows/pipeline.yml", ".github/workflows/pr-gates.yml",
    ".github/workflows/spec-to-pr.yml", "governance/required-workflows.json",
    "deploy/admission/policy.json", "deploy/flags.json", "deploy/gitops/production.json", "deploy/rollout/canary.json",
    "deploy/test-sandbox/policy.json",
    "docs/adr/ADR-044-delivery-pipeline-stages-and-verify-only-mode.md",
    "docs/adr/ADR-045-pipeline-security-and-protected-pipeline-changes.md",
    "docs/adr/ADR-046-gitops-desired-state-admission-and-drift.md",
    "docs/adr/ADR-047-canary-release-rollback-on-slo-and-ai-feature-kill-switches.md",
    "docs/adr/ADR-048-second-controls-for-c10-c11-and-a-blocking-control-for-c14.md",
    "governance/pipeline-guard.json", "infra/runbooks/release.md",
    "src/relay/release/__init__.py", "src/relay/release/flags.py", "src/relay/release/judged.py",
    "tests/test_pipeline_config.py", "tests/test_release_architecture.py", "tests/test_release_flags.py",
    "tests/test_release_judged.py", "tests/test_sandbox_run.py", "tools/sandbox_run.py",
    "tools/admit.py", "tools/security_gate.py",
}
MODIFIED = {
    ".github/CODEOWNERS", ".github/workflows/ci.yml", ".github/workflows/release.yml", "AGENTS.md", "governance/branch-protection.json",
    "pyproject.toml", "src/relay/__init__.py", "tests/test_service_app.py", "tests/test_service_http.py",
    "tests/test_service_wsgi.py", "tests/test_telemetry_signals.py",
}
SUITE = 959


def same(a, b) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == files(DATA_DIR)
    for rel in files(DATA_DIR):
        assert (tmp_path / rel).read_bytes() == (DATA_DIR / rel).read_bytes(), rel


def test_every_data_file_says_it_is_generated():
    for rel in sorted(files(DATA_DIR)):
        text = (DATA_DIR / rel).read_text(encoding="utf-8")
        assert "GENERATED" in text, rel
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["candidates"], manifest["train_releases"], manifest["deployment_records"]) == (12, 31, 10)
    assert len(list((DATA_DIR / "candidates").glob("*.json"))) == 12
    assert len(list((DATA_DIR / "train").glob("*.json"))) == 31


def test_vendored_lab_12_1_code_and_data_are_exact_copies():
    if not LAB_12_1.is_dir():  # the lab copied out of the book's repository
        return
    for name in ("__init__.py", "judge.py", "matrix.py", "probes.py"):
        assert same(LAB_ROOT / "vendor" / "redteam" / name, LAB_12_1 / "solution" / "redteam" / name), name
    for name in ("classes.json", "controls.json", "gate-policy.json"):
        assert same(LAB_ROOT / "vendor" / "redteam-data" / name, LAB_12_1 / "data" / name), name


def test_version_is_4_29_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.29.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.29.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_28_0():
    if not CANONICAL.is_dir():
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    assert ours - theirs == ADDED
    assert theirs - ours == set()
    assert {f for f in ours & theirs if not same(RELAY / f, CANONICAL / f)} == MODIFIED
    assert not any(f.startswith(("src/relay/agents/", "src/relay/service/", "src/relay/worker/", "infra/")) and
                   f != "infra/runbooks/release.md" for f in ADDED | MODIFIED)


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    env["PYTHONPATH"] = "src"
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=900, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(rf"\b{SUITE} passed\b", out.stdout), out.stdout[-500:]


def test_relay_lint_supply_chain_and_sandbox_checks_are_clean():
    for cmd in (["tools/lint.py"], ["tools/supplychain.py"], ["tools/sandbox_run.py", "check"]):
        out = subprocess.run([sys.executable, *cmd], cwd=RELAY, capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout[-1000:]

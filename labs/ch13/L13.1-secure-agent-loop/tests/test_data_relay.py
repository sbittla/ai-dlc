"""The generated data reproduces byte for byte, and Relay 4.25.0 in relay-repo/ is complete and passes its suite.

4.25.0 starts from canonical 4.23.0. The sets below are the exact files it adds and modifies, so a reviewer can
see that it leaves src/relay/escalation/, src/relay/audit/, src/relay/worker/ and governance/agents.json alone.
"""

import json
import os
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.23.0" / "relay-repo"
ADDED = {
    ".github/workflows/release.yml", ".pre-commit-config.yaml", "requirements-dev.txt",
    "docs/adr/ADR-028-mirror-only-dependencies-and-pinned-artefacts.md",
    "docs/adr/ADR-029-security-gates-for-agent-written-changes.md",
    "docs/adr/ADR-030-signed-sbom-ai-bom-and-provenance.md", "docs/adr/ADR-031-deployment-wiring-and-migration-role.md",
    "infra/runbooks/deploy.md", "security/gates.json", "security/gitleaks.toml", "security/semgrep.yml",
    "security/suppressions.json", "src/relay/service/migrate.py", "supply-chain/ai-components.json",
    "supply-chain/images.json", "supply-chain/mirror.json", "tests/test_infra_deploy_wiring.py", "tests/test_sbom.py",
    "tests/test_service_migrate.py", "tests/test_supply_chain.py", "tools/sbom.py", "tools/supplychain.py",
}
MODIFIED = {
    ".devcontainer/devcontainer.json", ".github/CODEOWNERS", ".github/workflows/ci.yml", "AGENTS.md",
    "deploy/Containerfile", "deploy/egress-proxy/Containerfile", "deploy/egress-proxy/allowlist.txt",
    "deploy/requirements.txt", "governance/branch-protection.json", "governance/waivers.json", "infra/compute.tf",
    "infra/db/roles.sql", "infra/iam.tf", "infra/nonprod.tfvars", "infra/runbooks/restore-test.md",
    "infra/variables.tf", "pyproject.toml", "src/relay/__init__.py", "src/relay/service/app.py",
    "src/relay/service/wsgi.py", "tests/test_infra_db_roles.py", "tests/test_infra_egress.py",
    "tests/test_service_app.py", "tests/test_service_http.py", "tests/test_service_wsgi.py",
}
SUITE = 524


def same(a, b) -> bool:
    """Equal apart from line endings: the baselines are stored as checked in (some CRLF), and a checkout may convert."""
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
        if rel.endswith(".json") and not rel.endswith(".cdx.json"):  # BOMs are Relay's tools/sbom.py output
            assert "GENERATED" in (DATA_DIR / rel).read_text(encoding="utf-8"), rel
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["changes"], manifest["seeded"], manifest["clean"]) == (160, 100, 60)


def test_version_is_4_25_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.25.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.25.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_23_0():
    if not CANONICAL.is_dir():  # the lab copied out of the book's repository
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    assert ours - theirs == ADDED
    assert theirs - ours == set()
    changed = {f for f in ours & theirs if not same(RELAY / f, CANONICAL / f)}
    assert changed == MODIFIED
    assert not any(f.startswith(("src/relay/escalation/", "src/relay/audit/", "src/relay/worker/",
                                 "src/relay/agents/")) for f in changed | ADDED)
    assert "governance/agents.json" not in changed


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=600, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(rf"\b{SUITE} passed\b", out.stdout), out.stdout[-500:]


def test_relay_lint_and_supply_chain_check_are_clean():
    for cmd in (["tools/lint.py"], ["tools/supplychain.py"]):
        out = subprocess.run([sys.executable, *cmd], cwd=RELAY, capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout[-1000:]

"""Relay 4.23.0 (Chapter 14 branch) is in this lab, complete, with its own test suite. These tests run it.

4.23.0 starts from canonical 4.21.0 and adds files. It modifies only version strings (pyproject, __init__ and
three version assertions), AGENTS.md, .github/CODEOWNERS, infra/iam.tf (one deny statement) and
infra/runbooks/bootstrap.md and governance/branch-protection.json (push restrictions on main). It does not touch src/relay/escalation/ or src/relay/worker/.
"""

import filecmp
import os
import re
import subprocess
import sys

from conftest import LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.21.0" / "relay-repo"
ADDED = {
    "src/relay/audit/__init__.py", "src/relay/audit/identity.py", "src/relay/audit/killswitch.py",
    "src/relay/audit/redact.py", "src/relay/audit/trail.py",
    "tests/test_audit_identity.py", "tests/test_audit_killswitch.py", "tests/test_audit_redact.py",
    "tests/test_audit_trail.py", "tests/test_audit_registry_file.py", "tests/test_audit_architecture.py",
    "tests/test_infra_agent_identity.py",
    "docs/adr/ADR-020-agent-identity-short-lived-tokens.md", "docs/adr/ADR-021-audit-trail-of-agent-actions.md",
    "docs/adr/ADR-022-detection-rules-and-kill-switch.md", "docs/adr/ADR-023-privacy-for-prompts-logs-and-traces.md",
    "governance/agents.json", "infra/agents.tf", "infra/detection/rules.json", "infra/runbooks/kill-switch.md",
    "infra/runbooks/break-glass.md", "infra/runbooks/ai-incident-playbook.md",
}
MODIFIED = {"pyproject.toml", "src/relay/__init__.py", "tests/test_service_app.py", "tests/test_service_http.py",
            "tests/test_service_wsgi.py", "AGENTS.md", ".github/CODEOWNERS", "infra/iam.tf",
            "infra/runbooks/bootstrap.md", "governance/branch-protection.json"}


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}


def test_version_is_4_23_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.23.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.23.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_21_0():
    if not CANONICAL.is_dir():  # the lab copied out of the book's repository
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    assert ours - theirs == ADDED
    assert theirs - ours == set()
    changed = {f for f in ours & theirs if not filecmp.cmp(RELAY / f, CANONICAL / f, shallow=False)}
    assert changed == MODIFIED
    assert not any(f.startswith(("src/relay/escalation/", "src/relay/worker/")) for f in changed | ADDED)


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=600, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(r"\b397 passed\b", out.stdout), out.stdout[-500:]


def collected(root):
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=root,
                         capture_output=True, text=True, timeout=600, env=env)
    return int(re.search(r"(\d+) tests? collected", out.stdout).group(1))


def test_the_suite_is_canonical_4_21_0_plus_72_new_tests():
    if not CANONICAL.is_dir():
        return
    assert (collected(CANONICAL), collected(RELAY)) == (325, 325 + 72)


def test_relay_lint_passes():
    out = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout


def test_agents_file_names_the_audit_package_and_the_token_boundary():
    text = (RELAY / "AGENTS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 150
    assert "src/relay/audit/" in text and "15-minute tokens" in text and "relay.audit.redact" in text


def test_identity_files_have_security_owners():
    owners = (RELAY / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for path in ("/src/relay/audit/", "/governance/agents.json", "/infra/agents.tf", "/infra/detection/"):
        assert re.search(rf"^{re.escape(path)}\s+@relay/security$", owners, re.M), path

"""Relay 4.21.0 is in this lab, complete, with its own test suite. These tests run it.

4.21.0 adds files to canonical 4.19.0 and changes only version strings, AGENTS.md and
.github/CODEOWNERS. It modifies no other file under src/ or tests/.
"""

import os
import re
import subprocess
import sys

from conftest import RELAY

ADDED = [
    "src/relay/service/sharedlimit.py", "src/relay/service/wsgi.py",
    "tests/test_service_sharedlimit.py", "tests/test_service_wsgi.py", "tests/test_infra_egress.py",
    "tests/test_infra_db_roles.py",
    "docs/adr/ADR-012-cloud-foundation-guardrails-iac.md", "docs/adr/ADR-013-private-network-and-egress.md",
    "docs/adr/ADR-014-managed-data-and-database-roles.md", "docs/adr/ADR-015-fargate-and-container-image.md",
    "infra/versions.tf", "infra/providers.tf", "infra/variables.tf", "infra/nonprod.tfvars", "infra/network.tf",
    "infra/endpoints.tf", "infra/security_groups.tf", "infra/compute.tf", "infra/iam.tf", "infra/data.tf",
    "infra/budget.tf", "infra/org/main.tf", "infra/org/scp-deny-regions.json",
    "infra/org/scp-deny-instance-types.json", "infra/org/scp-protect-baseline.json",
    "infra/org/scp-private-models-and-tags.json", "infra/db/roles.sql", "infra/runbooks/teardown.md",
    "infra/runbooks/restore-test.md", "infra/runbooks/bootstrap.md", "deploy/Containerfile", "deploy/requirements.txt",
    "deploy/egress-proxy/Containerfile", "deploy/egress-proxy/squid.conf", "deploy/egress-proxy/allowlist.txt",
]


def test_version_is_4_21_0_with_no_new_python_dependency():
    assert 'version = "4.21.0"' in (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "4.21.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")
    assert "dependencies = []" in (RELAY / "pyproject.toml").read_text(encoding="utf-8")


def test_added_files_exist():
    assert [f for f in ADDED if not (RELAY / f).is_file()] == []


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=600, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(r"\b147 passed\b", out.stdout), out.stdout[-500:]


def test_relay_lint_passes():
    out = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout


def test_agents_file_names_infra_and_forbids_apply():
    text = (RELAY / "AGENTS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 150
    assert "infra/" in text and "tofu apply" in text


def test_infra_and_guardrails_have_human_owners():
    owners = (RELAY / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert re.search(r"^/infra/\s+@relay/platform-leads", owners, re.M)
    assert re.search(r"^/infra/org/\s+@relay/security", owners, re.M)
    assert re.search(r"^/deploy/egress-proxy/\s+@relay/security", owners, re.M)

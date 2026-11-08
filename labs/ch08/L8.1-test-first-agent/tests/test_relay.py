"""Relay 4.20.0 in <target>/relay-repo: its own suite, lint, version, and exactly which files changed since 4.19.0.

Until you implement add_business_minutes and the message builders (README step 5),
Relay's suite stops with NotImplementedError.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from conftest import REFERENCE_REPO, RELAY_REPO

from testfirst.report import changed_files

ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

ADDED = [
    "docs/adr/ADR-009-escalation-http-routes-openapi.md",
    "docs/adr/ADR-010-business-hours-time-zones.md",
    "docs/adr/ADR-011-escalation-engine-storage-outbox.md",
    "specs/001-escalation-rules/contracts/escalation-api.openapi.json",
    "specs/001-escalation-rules/test-strategy.md",
    "src/relay/escalation/delivery.py",
    "src/relay/escalation/engine.py",
    "src/relay/escalation/hours.py",
    "src/relay/escalation/store.py",
    "src/relay/service/escalation_routes.py",
    "src/relay/service/responses.py",
    "tests/escalation/props.py",
    "tests/escalation/test_escalation_delivery.py",
    "tests/escalation/test_escalation_engine.py",
    "tests/escalation/test_escalation_hours.py",
    "tests/escalation/test_escalation_properties.py",
    "tests/escalation/test_escalation_zones.py",
    "tests/service_helpers.py",
    "tests/test_service_escalation.py",
    "tests/test_service_openapi.py",
]
MODIFIED = [
    ".github/CODEOWNERS",
    "AGENTS.md",
    "pyproject.toml",
    "specs/001-escalation-rules/contracts/escalation-rules.schema.json",
    "specs/001-escalation-rules/spec.md",
    "specs/001-escalation-rules/tasks.md",
    "src/relay/__init__.py",
    "src/relay/escalation/__init__.py",
    "src/relay/escalation/contract.py",
    "src/relay/escalation/evaluate.py",
    "src/relay/escalation/model.py",
    "src/relay/escalation/rules.py",
    "src/relay/service/__init__.py",
    "src/relay/service/__main__.py",
    "src/relay/service/app.py",
    "tests/escalation/escalation_fixtures.py",
    "tests/escalation/test_escalation_acceptance.py",
    "tests/escalation/test_escalation_contract.py",
    "tests/escalation/test_escalation_policy.py",
    "tests/test_architecture.py",
    "tests/test_service_app.py",
    "tests/test_service_http.py",
]


def test_relay_suite_passes():
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY_REPO, env=ENV,
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 and "NotImplementedError" in proc.stdout:
        raise NotImplementedError("relay-repo stops with NotImplementedError: write the tests (steps 2 and 3), then "
                                  "implement add_business_minutes and the message builders (step 5)")
    assert proc.returncode == 0, proc.stdout[-2000:]


def test_relay_lint_passes():
    lint = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY_REPO, env=ENV, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout


def test_version_is_4_20_0_and_spec_1_1_0():
    text = (RELAY_REPO / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")
    spec = (RELAY_REPO / "src" / "relay" / "escalation" / "__init__.py").read_text(encoding="utf-8")
    assert '__version__ = "4.20.0"' in text and 'SPEC_VERSION = "1.1.0"' in spec


ABUSE_TESTS = "tests/test_service_abuse.py"  # the Security track's file (README step 6S), optional


def test_changes_since_4_19_0_are_exactly_the_ones_chapter_8_lists():
    added, modified = changed_files(RELAY_REPO)
    assert [a for a in added if a != ABUSE_TESTS] == ADDED
    assert modified == MODIFIED


def test_nothing_under_infra_or_deploy():
    assert not (RELAY_REPO / "infra").exists() and not (RELAY_REPO / "deploy").exists()


def test_security_track_abuse_tests_pass_on_the_reference_code():
    mine = RELAY_REPO / ABUSE_TESTS
    if not mine.exists():
        pytest.skip("Security track only: no tests/test_service_abuse.py yet (README step 6S)")
    with tempfile.TemporaryDirectory(prefix="abuse-") as tmp:
        work = Path(tmp) / "relay-repo"
        shutil.copytree(REFERENCE_REPO, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        shutil.copyfile(mine, work / ABUSE_TESTS)
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", ABUSE_TESTS], cwd=work,
                              env=ENV, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert " passed" in proc.stdout and proc.stdout.count("passed") >= 1

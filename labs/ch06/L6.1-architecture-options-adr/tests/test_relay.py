"""Relay 4.19.0 is in this lab, complete, with its own test suite. These tests run it."""

import os
import re
import subprocess
import sys

from conftest import RELAY

NEW_FILES = [
    "src/relay/service/__init__.py", "src/relay/service/__main__.py", "src/relay/service/app.py",
    "src/relay/service/directory.py", "src/relay/service/ratelimit.py",
    "src/relay/worker/__init__.py", "src/relay/worker/__main__.py", "src/relay/worker/queue.py",
    "src/relay/worker/runner.py", "src/relay/worker/triage.py",
    "tests/test_architecture.py", "tests/test_service_app.py", "tests/test_service_http.py",
    "tests/test_worker_queue.py", "tests/test_worker_runner.py",
    "docs/adr/ADR-007-modular-monolith-async-triage.md", "docs/adr/ADR-008-standard-library-http.md",
]


def test_version_is_4_19_0():
    assert 'version = "4.19.0"' in (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "4.19.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")
    assert "dependencies = []" in (RELAY / "pyproject.toml").read_text(encoding="utf-8")


def test_new_packages_and_records_exist():
    missing = [f for f in NEW_FILES if not (RELAY / f).is_file()]
    assert missing == []


def test_relay_suite_passes():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=300, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(r"\b88 passed\b", out.stdout), out.stdout[-500:]


def test_relay_lint_passes():
    out = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout


def test_agents_file_stays_within_150_lines_and_names_the_new_packages():
    text = (RELAY / "AGENTS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 150
    assert "src/relay/service/" in text and "src/relay/worker/" in text and "docs/adr/" in text

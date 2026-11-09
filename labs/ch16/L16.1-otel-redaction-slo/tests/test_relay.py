"""Relay 4.27.0 (Chapter 16 branch) is in this lab, complete, with its own suite. These tests run it.

4.27.0 starts from canonical 4.25.0 and adds files. It modifies only version strings (pyproject, __init__ and the
three version assertions), AGENTS.md, .github/CODEOWNERS, `relay/service/wsgi.py` and `__main__.py` (telemetry
wiring) and `infra/runbooks/ai-incident-playbook.md` (deployed detection). It does not touch the worker, the agent
runtime, the escalation engine, the audit package, the store, the shared limiter or governance/agents.json.
"""

import filecmp
import os
import re
import subprocess
import sys

from conftest import LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.25.0" / "relay-repo"
MODIFIED = {"pyproject.toml", "src/relay/__init__.py", "tests/test_service_app.py", "tests/test_service_http.py",
            "tests/test_service_wsgi.py", "AGENTS.md", ".github/CODEOWNERS", "src/relay/service/wsgi.py",
            "src/relay/service/__main__.py", "infra/runbooks/ai-incident-playbook.md"}
ADDED_PREFIXES = ("src/relay/telemetry/", "docs/slo/", "infra/monitoring/", "tests/test_telemetry_",
                  "docs/adr/ADR-036-", "docs/adr/ADR-037-", "docs/adr/ADR-038-", "docs/adr/ADR-039-")
ADDED_FILES = {"src/relay/service/telemetry.py", "src/relay/service/pager.py", "src/relay/service/monitor.py",
               "infra/detection/service-rules.json", "tests/test_monitoring_config.py",
               "infra/runbooks/incident-response.md", "infra/runbooks/worker-stalled.md",
               "infra/runbooks/db-latency.md", "infra/runbooks/credential-stuffing.md", "infra/runbooks/game-day.md"}
UNTOUCHED = ("src/relay/worker/", "src/relay/agents/", "src/relay/escalation/", "src/relay/audit/",
             "src/relay/store.py", "src/relay/service/sharedlimit.py", "governance/agents.json", "deploy/egress-proxy/")


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}


def same(a, b):
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def test_version_is_4_27_0_with_no_new_python_dependency():
    text = (RELAY / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "4.27.0"' in text and "dependencies = []" in text
    assert '__version__ = "4.27.0"' in (RELAY / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")


def test_only_the_declared_files_differ_from_canonical_4_25_0():
    if not CANONICAL.is_dir():  # the lab copied out of the book's repository
        return
    ours, theirs = files(RELAY), files(CANONICAL)
    added = ours - theirs
    assert theirs - ours == set()
    assert {f for f in added if not (f in ADDED_FILES or f.startswith(ADDED_PREFIXES))} == set()
    changed = {f for f in ours & theirs if not same(RELAY / f, CANONICAL / f)}
    assert changed == MODIFIED
    assert not [f for f in changed | added if f.startswith(UNTOUCHED)]


def test_relay_suite_passes_with_747_tests():
    env = {k: v for k, v in os.environ.items() if k != "LAB_TARGET"}
    env["PYTHONPATH"] = "src"
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY,
                         capture_output=True, text=True, timeout=900, env=env)
    assert out.returncode == 0, out.stdout[-2000:]
    assert re.search(r"\b747 passed\b", out.stdout), out.stdout[-500:]


def test_relay_lint_passes():
    out = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout


def test_agents_file_and_owners():
    text = (RELAY / "AGENTS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 150 and "src/relay/telemetry/" in text and "semconv.ALLOWED" in text
    owners = (RELAY / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for path in ("/src/relay/telemetry/redact.py", "/src/relay/telemetry/semconv.py", "/infra/monitoring/"):
        assert re.search(rf"^{re.escape(path)}\s+@relay/security", owners, re.M), path

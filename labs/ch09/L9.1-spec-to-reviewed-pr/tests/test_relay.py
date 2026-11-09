"""Relay 4.22.0 in <target>/relay-repo: its own suite, lint, version, and exactly which files changed since 4.21.0.

Until you implement the two deletion functions (README step 4), Relay's
suite stops with NotImplementedError.
"""

import os
import subprocess
import sys

from conftest import BASE_REPO, DATA_DIR, RELAY_REPO

from prkit import series

ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
FORBIDDEN = ("infra/", "deploy/", "src/relay/service/sharedlimit.py", "src/relay/service/wsgi.py",
             "governance/")  # Chapters 11, 13 and 14's files, and governance, which this chapter must not change


def test_relay_suite_passes():
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY_REPO, env=ENV,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    if proc.returncode != 0 and "NotImplementedError" in proc.stdout:
        raise NotImplementedError("relay-repo stops with NotImplementedError: implement EscalationStore.delete_rule "
                                  "and engine.delete_rule (step 4)")
    assert proc.returncode == 0, proc.stdout[-2000:]


def test_relay_lint_passes():
    lint = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY_REPO, env=ENV, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout


def test_version_is_4_22_0():
    text = (RELAY_REPO / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")
    assert '__version__ = "4.22.0"' in text
    assert 'version = "4.22.0"' in (RELAY_REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_every_change_since_4_21_0_belongs_to_a_pull_request_and_none_touches_forbidden_paths():
    changed = series.changes(BASE_REPO, RELAY_REPO)
    assert series.unassigned(DATA_DIR, RELAY_REPO) == []
    assert [p for p in changed if p.startswith(FORBIDDEN)] == []


def test_spec_1_2_0_counts_the_chapter_quotes():
    spec_dir = RELAY_REPO / "specs" / "001-escalation-rules"
    spec = (spec_dir / "spec.md").read_text(encoding="utf-8")
    tasks = (spec_dir / "tasks.md").read_text(encoding="utf-8")
    criteria = [line for line in spec.splitlines() if line.startswith("### ESC-AC")]
    constraints = [line for line in spec.splitlines() if line.startswith("### SEC-")]
    assert "Version: 1.2.0" in spec and "Approved on: 2026-12-11" in spec
    assert (len(criteria), len(constraints), tasks.count("\n### T")) == (24, 9, 25)
    assert "### ESC-AC25\nRequirement: ESC-N06\nCoverage: full\n" in spec


def test_the_review_checklist_has_the_21_items_the_chapter_quotes():
    import re

    text = (DATA_DIR.parent / "templates" / "review-checklist.md").read_text(encoding="utf-8")
    items = [int(n) for n in re.findall(r"^(\d+)\. ", text, re.M)]
    assert items == list(range(1, 22))

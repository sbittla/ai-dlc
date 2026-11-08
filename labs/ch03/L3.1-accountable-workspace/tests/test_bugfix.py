"""RLY-412: the due-date fix in <target>/relay-repo, and the test that should have caught it.

Until you fix the defect, the first two tests stop with NotImplementedError
and tell you which README step comes next.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from datetime import date

import pytest
from conftest import DATA_DIR, FIXTURES, RELAY_REPO, TARGET

from relay.duedates import display_due_date
from relay.timezones import OFFSETS

DUE = date(2026, 11, 20)
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def run_suite(repo):
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo, env=ENV,
                          capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr


def suite_with_buggy_module(tmp_path):
    copy = tmp_path / "relay-repo"
    shutil.copytree(RELAY_REPO, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    shutil.copyfile(FIXTURES / "buggy_duedates.py", copy / "src" / "relay" / "duedates.py")
    return run_suite(copy)


def buggy_display():
    spec = importlib.util.spec_from_file_location("relay._buggy_duedates", FIXTURES / "buggy_duedates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.display_due_date


def test_relay_suite_catches_the_defect(tmp_path):
    code, last = suite_with_buggy_module(tmp_path)
    if code == 0:
        raise NotImplementedError("RLY-412: no test in relay-repo/tests fails on the unfixed code yet. "
                                  "Write the failing test first (README step 4).")
    assert code == 1, f"the suite should fail with test failures, not errors: {last}"


def test_every_viewer_sees_the_stored_due_date():
    if display_due_date(DUE, "Pacific/Auckland") == date(2026, 11, 19):
        raise NotImplementedError("RLY-412: Auckland still sees 2026-11-19. Fix display_due_date (README step 5).")
    assert {zone: display_due_date(DUE, zone) for zone in OFFSETS} == {zone: DUE for zone in OFFSETS}


def test_relay_suite_and_lint_pass():
    code, last = run_suite(RELAY_REPO)
    assert code == 0, last
    lint = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY_REPO, env=ENV, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout


def test_unknown_zones_are_still_rejected():
    with pytest.raises(KeyError):
        display_due_date(DUE, "Mars/Olympus_Mons")


# ---------------------------------------------------- numbers Chapter 3 quotes

def test_defect_affects_the_four_zones_more_than_12_hours_ahead():
    buggy = buggy_display()
    wrong = sorted(z for z in OFFSETS if buggy(DUE, z) != DUE)
    assert wrong == ["Pacific/Auckland", "Pacific/Chatham", "Pacific/Kiritimati", "Pacific/Tongatapu"]
    assert all(OFFSETS[z] > 12 * 60 for z in wrong) and len(OFFSETS) == 14
    assert buggy(DUE, "Pacific/Auckland") == date(2026, 11, 19)


def test_due_date_table_tool_on_the_before_snapshot():
    proc = subprocess.run([sys.executable, "tools/due_date_table.py", "--date", "2026-11-20"],
                          cwd=DATA_DIR / "repos" / "before", env=ENV, capture_output=True, text=True)
    assert "| Pacific/Auckland | +13:00 | 2026-11-19  <-- differs |" in proc.stdout
    assert "Zones showing a different date: 4 of 14" in proc.stdout


def test_before_snapshot_suite_passes_with_the_defect():
    code, last = run_suite(DATA_DIR / "repos" / "before")
    assert code == 0 and last.startswith("14 passed")


@pytest.mark.skipif(TARGET != "solution", reason="reference counts; your own test count may differ")
def test_reference_suite_counts(tmp_path):
    assert run_suite(RELAY_REPO)[1].startswith("29 passed")
    code, last = suite_with_buggy_module(tmp_path)
    assert code == 1 and last.startswith("5 failed, 24 passed")

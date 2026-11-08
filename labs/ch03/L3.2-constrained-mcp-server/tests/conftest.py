"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest   # same, PowerShell
"""

import os
import sys
from pathlib import Path

import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent
TARGET = os.environ.get("LAB_TARGET", "starter")
if TARGET not in {"starter", "solution"}:
    raise SystemExit(f"LAB_TARGET must be 'starter' or 'solution', got {TARGET!r}")

sys.path.insert(0, str(LAB_ROOT / TARGET))
DATA_DIR = LAB_ROOT / "data"
SQL = DATA_DIR / "relay-test.sql"


def pytest_report_header(config):
    return f"Lab 3.2 tests running against: {TARGET}/"


@pytest.fixture
def conn():
    from relaymcp.db import open_readonly
    c = open_readonly(SQL)
    yield c
    c.close()


@pytest.fixture
def audit():
    from relaymcp.policy import AuditLog
    return AuditLog(clock=lambda: "2026-11-08T09:00:00+00:00")

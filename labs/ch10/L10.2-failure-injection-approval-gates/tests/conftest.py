"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest; Remove-Item Env:LAB_TARGET   # same, PowerShell

Three things are graded, all in <target>/faultlab/: open_pull_request (github.py), resume (recover.py)
and verdict (drills.py).
"""

import os
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
TARGET = os.environ.get("LAB_TARGET", "starter")
if TARGET not in {"starter", "solution"}:
    raise SystemExit(f"LAB_TARGET must be 'starter' or 'solution', got {TARGET!r}")

TARGET_DIR = LAB_ROOT / TARGET
DATA_DIR = LAB_ROOT / "data"
sys.path.insert(0, str(TARGET_DIR))
sys.path.insert(0, str(DATA_DIR / "relay-4.24.0" / "src"))


def pytest_report_header(config):
    return f"Lab 10.2 tests running against: {TARGET}/"

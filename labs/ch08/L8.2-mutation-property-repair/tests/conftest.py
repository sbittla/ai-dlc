"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest; Remove-Item Env:LAB_TARGET   # same, PowerShell

Graded: the mutation operators and score in <target>/mutate/, and your repaired
suite in <target>/suite/test_repaired.py.
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
CORE = "rules,evaluate,hours"

sys.path.insert(0, str(TARGET_DIR))


def pytest_report_header(config):
    return f"Lab 8.2 tests running against: {TARGET}/"

"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest; Remove-Item Env:LAB_TARGET   # same, PowerShell

Two things are graded: the pull-request kit in <target>/prkit/ (check_pr and
verify_claim), and Relay 4.22.0's rule deletion in <target>/relay-repo/
(EscalationStore.delete_rule and engine.delete_rule).
"""

import os
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
TARGET = os.environ.get("LAB_TARGET", "starter")
if TARGET not in {"starter", "solution"}:
    raise SystemExit(f"LAB_TARGET must be 'starter' or 'solution', got {TARGET!r}")

TARGET_DIR = LAB_ROOT / TARGET
RELAY_REPO = TARGET_DIR / "relay-repo"
REFERENCE_REPO = LAB_ROOT / "solution" / "relay-repo"
DATA_DIR = LAB_ROOT / "data"
BASE_REPO = DATA_DIR / "relay-4.21.0"

sys.path.insert(0, str(TARGET_DIR))


def pytest_report_header(config):
    return f"Lab 9.1 tests running against: {TARGET}/"

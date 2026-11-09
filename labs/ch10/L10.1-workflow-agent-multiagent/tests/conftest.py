"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest; Remove-Item Env:LAB_TARGET   # same, PowerShell

Four things are graded: Meter.check, Meter.admit and stop_reason in <target>/relay-repo/src/relay/agents/,
and run_workflow and compare in <target>/agentlab/.
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
BASELINE = LAB_ROOT.parent.parent / "relay-baselines" / "4.23.0" / "relay-repo"
DATA_DIR = LAB_ROOT / "data"

sys.path.insert(0, str(TARGET_DIR))
sys.path.insert(0, str(RELAY_REPO / "src"))


def pytest_report_header(config):
    return f"Lab 10.1 tests running against: {TARGET}/"

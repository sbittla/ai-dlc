"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest   # same, PowerShell

Two things are graded: the workspace audit in <target>/audit/, and the RLY-412
fix in <target>/relay-repo/.
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
TARGET = os.environ.get("LAB_TARGET", "starter")
if TARGET not in {"starter", "solution"}:
    raise SystemExit(f"LAB_TARGET must be 'starter' or 'solution', got {TARGET!r}")

TARGET_DIR = LAB_ROOT / TARGET
RELAY_REPO = TARGET_DIR / "relay-repo"
DATA_DIR = LAB_ROOT / "data"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# data/repos/before holds fake secrets, so it is generated, never committed.
if not (DATA_DIR / "repos" / "before" / "AGENTS.md").is_file():
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py")], check=True)

sys.path.insert(0, str(RELAY_REPO / "src"))
sys.path.insert(0, str(TARGET_DIR))


def pytest_report_header(config):
    return f"Lab 3.1 tests running against: {TARGET}/"

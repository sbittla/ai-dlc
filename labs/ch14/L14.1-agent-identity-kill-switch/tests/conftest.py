"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest; Remove-Item Env:LAB_TARGET   # same, PowerShell
"""

import json
import os
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
TARGET = os.environ.get("LAB_TARGET", "starter")
if TARGET not in {"starter", "solution"}:
    raise SystemExit(f"LAB_TARGET must be 'starter' or 'solution', got {TARGET!r}")

sys.path.insert(0, str(LAB_ROOT / TARGET))
DATA_DIR = LAB_ROOT / "data"
RELAY = LAB_ROOT / "relay-repo"
POLICY = json.loads((DATA_DIR / "identities" / "identity-policy.json").read_text(encoding="utf-8"))

import agentsec  # noqa: E402,F401  (puts relay-repo/src and vendor/ on the path)


def pytest_report_header(config):
    return f"Lab 14.1 tests running against: {TARGET}/"

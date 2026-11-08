"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest   # same, PowerShell
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
MAPPING = json.loads((DATA_DIR / "mapping.json").read_text(encoding="utf-8"))
WORKLOAD = json.loads((DATA_DIR / "workload.json").read_text(encoding="utf-8"))
PRICES = {p: json.loads((DATA_DIR / "prices" / f"{p}-2026-11.json").read_text(encoding="utf-8")) for p in ("aws", "azure", "gcp")}
REQUIRED = json.loads((DATA_DIR / "required-concerns.json").read_text(encoding="utf-8"))["concerns"]


def pytest_report_header(config):
    return f"Lab 11.2 tests running against: {TARGET}/"

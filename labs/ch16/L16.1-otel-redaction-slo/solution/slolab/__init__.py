"""slolab: Lab 16.1's tools for telemetry redaction, SLO burn-rate alerts, error budgets and runtime checks.

Importing the package puts Relay 4.27.0 (`relay-repo/src`) on the import path, so `relay.telemetry` is the
lab's own copy.
"""

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
RELAY = LAB_ROOT / "relay-repo"
if str(RELAY / "src") not in sys.path:
    sys.path.insert(0, str(RELAY / "src"))

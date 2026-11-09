"""gameday: Lab 16.2's tools for checking an incident assistant's hypotheses, gating remediation, replaying a
game day and checking a postmortem.

Importing the package puts `vendor/` on the import path: a copy of Relay 4.27.0's `relay.telemetry` and
`relay.audit`, refreshed from Lab 16.1 by `scripts/generate_data.py`.
"""

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
VENDOR = LAB_ROOT / "vendor"
L161_RELAY = LAB_ROOT.parent / "L16.1-otel-redaction-slo" / "relay-repo"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

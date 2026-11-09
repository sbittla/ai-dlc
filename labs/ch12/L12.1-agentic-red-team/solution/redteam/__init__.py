"""Lab 12.1: a threat model and defence verification for Relay 4.26.0.

The lab does not attack a model. It lists the attack classes in Relay's threat model, records which Relay
controls are claimed against each, and probes each real control (in ../relay-repo) against each class.
"""

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
RELAY_SRC = LAB / "relay-repo" / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))

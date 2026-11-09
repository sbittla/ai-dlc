"""Lab 10.2: failure injection, approval gates and recovery on Relay 4.24.0's agent runtime.

The runtime (`relay.agents`, `relay.audit`) is Relay's code, copied into data/relay-4.24.0/ by
scripts/generate_data.py. The helper's model and GitHub are simulated and deterministic.
"""

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = LAB_ROOT / "data"
RELAY_SRC = DATA_DIR / "relay-4.24.0" / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))

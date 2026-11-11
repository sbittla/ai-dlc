"""Lab 19.1: a maintenance bot that proposes, proves and waits (Chapter 19).

The lab drives Relay 4.31.0's `relay.maintenance` package from `../relay-repo/src`. Nothing here installs a package
or reaches the network; code the bot did not write runs in Chapter 18's sandbox (real processes, inert).
"""

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
RELAY = LAB / "relay-repo"
RELAY_SRC = RELAY / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))

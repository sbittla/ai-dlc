"""Lab 19.2: a safety and security case for Relay's maintenance bot, with adversarial-input and budget tests.

The lab runs Relay 4.31.0 from Lab 19.1's `relay-repo/src` (the same chapter's branch), so do Lab 19.1's setup
first. Nothing here reaches the network; the sandbox cases start real, inert processes.
"""

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
RELAY = LAB.parent / "L19.1-maintenance-bot" / "relay-repo"
if str(RELAY / "src") not in sys.path:
    sys.path.insert(0, str(RELAY / "src"))

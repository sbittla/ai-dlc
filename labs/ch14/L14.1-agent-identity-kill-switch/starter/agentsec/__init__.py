"""agentsec: Lab 14.1's tools for agent identity, detection, audit trails, drills and caller scoping.

Importing the package puts Relay 4.23.0 (`relay-repo/src`) and Lab 3.2's query tool (`vendor/`) on the
import path, so `relay.audit` and `relaymcp` are the lab's own copies.
"""

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
RELAY = LAB_ROOT / "relay-repo"
for _p in (RELAY / "src", LAB_ROOT / "vendor"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

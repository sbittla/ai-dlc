"""Lab 18.1: durable, sandboxed agent workers on Relay 4.30.0.

The lab's code imports Relay from `relay-repo/src`, the Chapter 18 branch in this lab's folder, so every drill
runs Relay's real queue, ledger, sandbox, registry state and agent runtime.
"""

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = LAB_ROOT / "data"
RELAY_SRC = LAB_ROOT / "relay-repo" / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))

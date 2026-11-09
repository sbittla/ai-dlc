"""Lab 10.1: one task, three designs (a workflow, a single agent, multiple agents), and the routed design.

The designs run on Relay 4.24.0's agent runtime (`relay.agents`) from this folder's relay-repo: its
budgets, stopping conditions, tool contracts, boundary, run state and approval gates are real code. The
model is simulated (`agentlab.sim`): seeded, deterministic, and configured in `data/simulator.json`.
"""

import sys
from pathlib import Path

RELAY_SRC = Path(__file__).resolve().parent.parent / "relay-repo" / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = LAB_ROOT / "data"

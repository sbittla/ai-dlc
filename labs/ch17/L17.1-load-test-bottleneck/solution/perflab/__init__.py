"""Lab 17.1: load-test Relay's service and worker, find the bottleneck, fix it and measure again.

The lab runs Relay 4.28.0 from this lab's relay-repo: its service, shared limiter, queue and worker are real
code. The traffic is synthetic (data/traffic/, generated); the triage model is simulated; the load-test runs
in data/measured/ were recorded on the author's machine and are this machine's numbers, not yours.
"""

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = LAB_ROOT / "data"
RELAY = LAB_ROOT / "relay-repo"
RELAY_SRC = RELAY / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))
if str(RELAY / "tools") not in sys.path:
    sys.path.insert(0, str(RELAY / "tools"))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

"""Lab 17.2: cost per successful triage across routing and caching configurations, and spend quotas.

Quality comes from Lab 7.1's simulator, dataset and statistics (copied here unchanged, plus one configured
profile). Latency, reasoning length and abuse traffic are configured in data/. Prices and quotas are Relay
4.28.0's `relay.routing`, copied into data/relay-4.28.0/ by scripts/generate_data.py. Nothing calls a model.
"""

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = LAB_ROOT / "data"
RELAY_SRC = DATA_DIR / "relay-4.28.0" / "src"
if str(RELAY_SRC) not in sys.path:
    sys.path.insert(0, str(RELAY_SRC))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

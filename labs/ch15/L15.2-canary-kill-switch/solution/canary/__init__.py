"""Lab 15.2: a canary release that rolls back on SLO burn, and a kill switch for an AI feature.

Everything is simulated: per-minute traffic and per-ticket outcomes are drawn deterministically from the
configured scenarios in data/. The policies and the kill switch are Relay 4.29.0's own, vendored from Lab 15.1:
`vendor/config/canary.json` (relay-canary-v1), `vendor/config/slos.json` (relay-slo-v1) and
`vendor/relay/release/flags.py`.
"""

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
VENDOR = LAB / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def policy() -> dict:
    return load_json(VENDOR / "config" / "canary.json")


def slos() -> dict:
    return {s["slo_id"]: s for s in load_json(VENDOR / "config" / "slos.json")["slos"]}

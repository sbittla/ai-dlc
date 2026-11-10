"""Lab 15.1: a hardened delivery pipeline for Relay 4.29.0, run in a deterministic simulator.

Nothing here contacts a registry, a cloud, a model or GitHub. Workflows are parsed from Relay's own
`.github/workflows/`; release candidates, scanner reports, signatures and deployment records are generated
(`scripts/generate_data.py`); the coverage gate runs Chapter 12's probes (vendored from Lab 12.1) on
`../relay-repo`.
"""

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
RELAY = LAB / "relay-repo"
for _p in (RELAY / "src", LAB / "vendor"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

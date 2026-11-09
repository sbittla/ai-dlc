"""govpack: Lab 14.2's checks for a governance pack (permission matrix, DPIA, licences, AI Act, claims)."""

import json
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

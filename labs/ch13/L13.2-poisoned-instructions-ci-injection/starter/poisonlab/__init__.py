"""poisonlab: Lab 13.2's checks for poisoned instruction files and prompt injection into CI agents."""

import json
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

"""Lab 18.2: an inference benchmark on a simulated serving model, and an optional real run.

Every number the reports print comes from `sim-open-1.5b` on `sim-accel-24`, configured in data/serving.json.
They show how memory, batching and quantization trade off; they are not measurements of any product.
"""

import json
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = LAB_ROOT / "data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))

"""Lab 20.2: design, power and read out a controlled adoption experiment (Chapter 20)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_changes(path: Path | None = None) -> list[dict]:
    """Rows of data/changes.csv with numbers converted."""
    rows = []
    with open(path or DATA / "changes.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            for k in ("author_hours", "review_hours", "review_wait_hours", "deploy_wait_hours", "lead_time_hours"):
                r[k] = float(r[k])
            r["failed"] = r["failed"] == "1"
            rows.append(r)
    return rows

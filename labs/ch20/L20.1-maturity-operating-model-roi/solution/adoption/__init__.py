"""Lab 20.1: a maturity assessment from evidence, a target operating model, an approved tool catalog and an ROI
model that keeps measured values apart from projections (Chapter 20)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Finding:
    rule: str
    subject: str
    message: str

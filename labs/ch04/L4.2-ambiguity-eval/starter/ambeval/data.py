"""Load the labelled statements and a detector lexicon (provided)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFECTS = ("ambiguity", "untestable", "contradiction", "missing_actor")
SPLITS = ("dev", "heldout")


@dataclass(frozen=True)
class Statement:
    id: str
    set: str
    split: str          # "dev" or "heldout"
    topic: str
    text: str
    defects: frozenset[str]
    conflicts_with: str | None


def load_statements(path: Path) -> list[Statement]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out.append(Statement(r["id"], r["set"], r["split"], r["topic"], r["text"],
                                     frozenset(r["defects"]), r["conflicts_with"]))
    return out


@dataclass(frozen=True)
class Lexicon:
    version: str
    vague_terms: tuple[str, ...]
    weak_modals: tuple[str, ...]
    quality_terms: tuple[str, ...]
    measurable_patterns: tuple[str, ...]
    actor_terms: tuple[str, ...]
    passive_pattern: str
    min_overlap: float
    min_overlap_polarity: float


def load_lexicon(path: Path) -> Lexicon:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Lexicon(raw["lexicon_version"], tuple(raw["vague_terms"]), tuple(raw["weak_modals"]),
                   tuple(raw["quality_terms"]), tuple(raw["measurable_patterns"]), tuple(raw["actor_terms"]),
                   raw["passive_pattern"], raw["contradiction"]["min_overlap"],
                   raw["contradiction"]["min_overlap_polarity"])

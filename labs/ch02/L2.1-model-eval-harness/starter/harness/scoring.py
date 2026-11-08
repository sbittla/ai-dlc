"""Turn raw model text into scored results (STARTER: implement the TODO functions)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass

from .schema import TRIAGE_SCHEMA, validate

FIELDS = ("category", "priority", "team")


@dataclass(frozen=True)
class Parsed:
    value: dict | None
    error: str | None  # None, "invalid_json" or "schema"
    detail: str = ""


def parse_output(text: str) -> Parsed:
    """Parse model text as JSON and validate it against TRIAGE_SCHEMA.

    Treat model output as untrusted input: no stripping of prose, no
    guessing, no repair. Text that is not exactly a JSON document is
    "invalid_json"; JSON that breaks the schema is "schema". Repairing output
    hides how often the model fails, which is the thing you are measuring.
    """
    # TODO(L2.1): implement using the definition in the docstring.
    raise NotImplementedError("parse_output")


def score_prediction(expected: dict, predicted: dict | None) -> dict[str, bool]:
    """Field-by-field exact match. An invalid prediction gets False for every field."""
    # TODO(L2.1): implement using the definition in the docstring.
    raise NotImplementedError("score_prediction")


def cost_usd(input_tokens: int, output_tokens: int, price_in_per_mtok: float, price_out_per_mtok: float) -> float:
    """Cost of one call in US dollars, from token counts and per-million-token prices."""
    # TODO(L2.1): implement using the definition in the docstring.
    raise NotImplementedError("cost_usd")


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Preferred over the simple "p ± 1.96·sqrt(p(1-p)/n)" because it behaves
    sensibly near 0 and 1 and for small n, which is where model evals live.
    """
    # TODO(L2.1): implement using the definition in the docstring.
    raise NotImplementedError("wilson_interval")


def consistency_rate(predictions: dict[str, list[tuple | None]]) -> float:
    """Share of tickets for which every repeat run gave the identical prediction.

    `predictions` maps ticket id -> list of predictions (one per run), each a
    (category, priority, team) tuple, or None when the output was invalid.
    An invalid output (None) is treated as one more possible answer: a ticket
    with some valid and some invalid runs is inconsistent, while a ticket that
    is invalid on every run counts as consistent (consistently unusable).
    """
    # TODO(L2.1): implement using the definition in the docstring.
    raise NotImplementedError("consistency_rate")


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (same definition as Lab 1.1)."""
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


def group_by(records, key):
    groups = defaultdict(list)
    for r in records:
        groups[key(r)].append(r)
    return groups

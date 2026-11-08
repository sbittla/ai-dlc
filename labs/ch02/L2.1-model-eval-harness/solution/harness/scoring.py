"""Turn raw model text into scored results (reference solution)."""

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
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        return Parsed(None, "invalid_json", str(exc))
    errors = validate(value, TRIAGE_SCHEMA)
    if errors:
        return Parsed(None, "schema", "; ".join(errors))
    return Parsed(value, None)


def score_prediction(expected: dict, predicted: dict | None) -> dict[str, bool]:
    """Field-by-field exact match. An invalid prediction gets False for every field."""
    if predicted is None:
        return {f: False for f in FIELDS}
    return {f: predicted.get(f) == expected[f] for f in FIELDS}


def cost_usd(input_tokens: int, output_tokens: int, price_in_per_mtok: float, price_out_per_mtok: float) -> float:
    """Cost of one call in US dollars, from token counts and per-million-token prices."""
    return input_tokens / 1_000_000 * price_in_per_mtok + output_tokens / 1_000_000 * price_out_per_mtok


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Preferred over the simple "p ± 1.96·sqrt(p(1-p)/n)" because it behaves
    sensibly near 0 and 1 and for small n, which is where model evals live.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def consistency_rate(predictions: dict[str, list[tuple | None]]) -> float:
    """Share of tickets for which every repeat run gave the identical prediction.

    `predictions` maps ticket id -> list of predictions (one per run), each a
    (category, priority, team) tuple, or None when the output was invalid.
    An invalid output (None) is treated as one more possible answer: a ticket
    with some valid and some invalid runs is inconsistent, while a ticket that
    is invalid on every run counts as consistent (consistently unusable).
    """
    if not predictions:
        raise ValueError("no predictions")
    stable = sum(1 for runs in predictions.values() if len(set(runs)) == 1)
    return stable / len(predictions)


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (same definition as Lab 1.1)."""
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


def group_by(records, key):
    groups = defaultdict(list)
    for r in records:
        groups[key(r)].append(r)
    return groups

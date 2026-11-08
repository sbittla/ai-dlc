"""Score predicted defects against labels (reference solution).

Two functions are TODOs in starter/: confusion and rates. wilson_interval is
provided: it is the Wilson score interval of Chapter 2 and Lab 2.1, unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .data import DEFECTS, Statement


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (as in Lab 2.1)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class Counts:
    tp: int
    fp: int
    fn: int
    tn: int


@dataclass(frozen=True)
class Rates:
    precision: float | None                      # None when nothing was flagged
    precision_ci: tuple[float, float] | None
    recall: float | None                         # None when nothing has the defect
    recall_ci: tuple[float, float] | None


# ------------------------------------------------------------------ TODO 1

def confusion(statements: list[Statement], predicted: dict[str, frozenset[str]], defect: str) -> Counts:
    """Counts for one defect type over `statements`.

    A statement is positive if `defect` is in its labels, and flagged if `defect`
    is in predicted[statement.id] (a missing id counts as nothing flagged).
    tp: positive and flagged; fp: flagged, not positive; fn: positive, not
    flagged; tn: neither.
    """
    tp = fp = fn = tn = 0
    for s in statements:
        positive = defect in s.defects
        flagged = defect in predicted.get(s.id, frozenset())
        if positive and flagged:
            tp += 1
        elif flagged:
            fp += 1
        elif positive:
            fn += 1
        else:
            tn += 1
    return Counts(tp, fp, fn, tn)


# ------------------------------------------------------------------ TODO 2

def rates(c: Counts) -> Rates:
    """Precision = tp / (tp + fp) and recall = tp / (tp + fn), each with its
    Wilson interval on that denominator. A rate whose denominator is zero is
    None, with a None interval: it is undefined, not 0% or 100%."""
    flagged, positive = c.tp + c.fp, c.tp + c.fn
    p = (c.tp / flagged, wilson_interval(c.tp, flagged)) if flagged else (None, None)
    r = (c.tp / positive, wilson_interval(c.tp, positive)) if positive else (None, None)
    return Rates(p[0], p[1], r[0], r[1])


# ------------------------------------------------------------------ provided

def micro(statements: list[Statement], predicted: dict[str, frozenset[str]]) -> Counts:
    """All four defect types pooled: one decision per (statement, defect type)."""
    totals = [confusion(statements, predicted, d) for d in DEFECTS]
    return Counts(*(sum(getattr(c, f) for c in totals) for f in ("tp", "fp", "fn", "tn")))

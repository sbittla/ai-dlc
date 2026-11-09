"""Probing a redactor for bypasses (TODO 1 is `score_probes`).

A probe is a string with a label: does it contain personal data or a credential? A redactor *catches* a
probe when it replaces at least one thing in it. For a sensitive probe that is a hit; for a benign probe it
is a false positive. The point of a probe set is the misses: each is either fixed or pinned as known.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    category: str
    sensitive: bool
    caught: bool

    @property
    def outcome(self) -> str:
        if self.sensitive:
            return "caught" if self.caught else "missed"
        return "false-positive" if self.caught else "left-alone"


def score_probes(redact: Callable[[str], tuple[str, Counter]], cases: list[dict]) -> list[ProbeResult]:
    """TODO 1. One ProbeResult per case, in order.

    `redact(text)` returns (clean_text, counts). The probe is caught when the counts are non-empty, that is
    when any value of `counts` is above zero. Copy `id`, `category` and `sensitive` from the case.
    """
    raise NotImplementedError("TODO 1: score_probes")


def summary(results: list[ProbeResult]) -> dict[str, dict[str, int]]:
    """Counts of outcomes per category (provided)."""
    table: dict[str, Counter] = {}
    for r in results:
        table.setdefault(r.category, Counter())[r.outcome] += 1
    return {k: dict(v) for k, v in table.items()}


def totals(results: list[ProbeResult]) -> dict[str, int]:
    return dict(Counter(r.outcome for r in results))

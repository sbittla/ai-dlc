"""Catch rates with honest intervals (TODO 4 in starter/)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials, as fractions (Chapter 2; provided)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class Row:
    name: str
    n: int
    pre_commit: int = 0      # blocked before the commit
    ci_only: int = 0         # passed pre-commit, blocked in CI
    escaped: int = 0         # passed both

    @property
    def caught(self) -> int:
        return self.pre_commit + self.ci_only


@dataclass
class CatchReport:
    rows: list[Row] = field(default_factory=list)   # one per seeded category, in first-seen order
    total: Row | None = None                         # all seeded changes
    by_scanner: dict[str, int] = field(default_factory=dict)  # seeded changes each scanner alone blocks
    clean_n: int = 0
    clean_blocked: int = 0                           # clean changes blocked at either stage


def catch_report(outcomes: dict[str, dict], truth: dict[str, dict]) -> CatchReport:
    """Summarize gate outcomes against the seeded truth.

    `outcomes[change]` has "pre-commit" and "ci" (gate statuses: 0 pass, 1 blocked) and "blocking_scanners"
    (the set of scanners with a blocking finding at either stage). `truth[change]` has "seeded" and
    "category". Iterate changes in sorted ID order. For seeded changes build one Row per category (rows in
    the order categories are first seen) and a total Row named "all seeded": pre_commit if pre-commit status
    is 1; ci_only if pre-commit passed and CI status is 1; escaped otherwise. by_scanner counts seeded
    changes whose blocking_scanners include each scanner, with keys sorted. For clean changes count clean_n
    and clean_blocked (blocked at either stage).
    """
    raise NotImplementedError("TODO 4: catch rates by category, stage and scanner")

"""Agreement between a judge and human labels, and probes for known judge biases (STARTER: implement the TODO functions)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    """Counts with 'pass' as the positive class. A missing verdict (None) counts as wrong."""

    tp: int  # judge pass, human pass
    fp: int  # judge pass, human fail  (a false pass: the costly error for a gate)
    fn: int  # judge fail or no verdict, human pass
    tn: int  # judge fail, human fail
    none: int = 0  # items with no verdict (already counted in fn or fp)

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n

    @property
    def false_pass_rate(self) -> float:
        """Share of human-failed answers that the judge passed."""
        failed = self.fp + self.tn
        return self.fp / failed if failed else 0.0


def confusion(human: list[str], judge: list[str | None]) -> Confusion:
    """Count agreement, with 'pass' as positive.

    human[i] is 'pass' or 'fail'; judge[i] is 'pass', 'fail' or None (no
    verdict: a refusal, truncation or API error). A None never counts as
    agreement: on a human 'pass' it counts as fn, and on a human 'fail' it
    counts as fp, so an unanswered item never looks like a correct rejection.
    `none` records how many Nones there were. Raise ValueError if the lists
    differ in length or are empty.
    """
    # TODO(L7.2): implement using the definition in the docstring.
    raise NotImplementedError("confusion")


def cohen_kappa(a: list[str | None], b: list[str | None]) -> float:
    """Cohen's kappa between two raters over the same items.

    p_o = share of items where a[i] == b[i]. p_e = sum over every label L
    seen in either list of (share of a equal to L) * (share of b equal to L).
    None is treated as a label of its own. kappa = (p_o - p_e) / (1 - p_e).
    If p_e == 1 (both raters used one and the same label throughout), return
    1.0. Raise ValueError if the lists differ in length or are empty.
    """
    # TODO(L7.2): implement using the definition in the docstring.
    raise NotImplementedError("cohen_kappa")


def kappa_interval(a: list, b: list, n_resamples: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95% percentile bootstrap interval for kappa, resampling items."""
    rng = random.Random(seed)
    n = len(a)
    ks = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        ks.append(cohen_kappa([a[i] for i in idx], [b[i] for i in idx]))
    ks.sort()
    return ks[int(0.025 * n_resamples)], ks[int(0.975 * n_resamples) - 1]


def swap_consistency(first_order: list[str | None], second_order: list[str | None]) -> float:
    """Share of pairs where the judge chose the same answer in both orders.

    first_order[i] is the judge's verdict ('A' or 'B') with the pair shown as
    (a, b); second_order[i] is its verdict with the same pair shown as (b, a).
    The same answer was chosen when the letters differ ('A' then 'B', or 'B'
    then 'A'). A None in either order is inconsistent. Raise ValueError if the
    lists differ in length or are empty.
    """
    # TODO(L7.2): implement using the definition in the docstring.
    raise NotImplementedError("swap_consistency")


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (copied from Lab 2.1)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)

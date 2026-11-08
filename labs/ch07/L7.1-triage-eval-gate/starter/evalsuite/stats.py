"""Statistics for comparing two candidates on the same tickets (STARTER: implement the TODO functions)."""

from __future__ import annotations

import math
import random
from statistics import NormalDist


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (copied from Lab 2.1)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar test on discordant pairs.

    b = tickets the baseline got right and the candidate got wrong;
    c = tickets the candidate got right and the baseline got wrong.
    Under "no difference", each discordant ticket is equally likely to fall
    either way, so min(b, c) follows Binomial(b + c, 0.5). The p-value is
    twice the lower tail, capped at 1. With no discordant tickets, p = 1.
    """
    # TODO(L7.1): implement using the definition in the docstring.
    raise NotImplementedError("mcnemar_exact")


def paired_bootstrap(diffs: list[float], n_resamples: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Mean of per-ticket differences and its 95% percentile bootstrap interval.

    rng = random.Random(seed). For each of n_resamples rounds, draw
    len(diffs) values with replacement using rng.choice, and record their
    mean. Sort the means; the interval is (means[int(0.025 * n_resamples)],
    means[int(0.975 * n_resamples) - 1]). Returns (mean, low, high).
    The same tickets are used for both candidates in every resample, which
    is what makes the comparison paired.
    """
    # TODO(L7.1): implement using the definition in the docstring.
    raise NotImplementedError("paired_bootstrap")


def cluster_bootstrap(clusters: list[list[float]], n_resamples: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Mean per-ticket difference and its 95% interval, resampling whole clusters (families).

    Tickets of one family share a problem, so they are not independent; resampling
    tickets one by one would make the interval too narrow. Here each cluster is
    the list of per-ticket differences of one family.

    rng = random.Random(seed); k = len(clusters). For each of n_resamples rounds,
    draw k cluster indices with rng.randrange(k), and record
    sum(sum(clusters[i]) for the drawn i) / sum(len(clusters[i]) for the drawn i).
    Sort the recorded means; the interval is (means[int(0.025 * n_resamples)],
    means[int(0.975 * n_resamples) - 1]). The point estimate is the mean over all
    tickets. Returns (mean, low, high). Raise ValueError if there are no tickets.
    """
    # TODO(L7.1): implement using the definition in the docstring.
    raise NotImplementedError("cluster_bootstrap")


def paired_sample_size(discordant_rate: float, delta: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Tickets needed to detect a paired accuracy difference `delta` (Connor, 1987).

    n = (z_a * sqrt(psi) + z_b * sqrt(psi - delta**2))**2 / delta**2, rounded
    up, where psi is the share of tickets on which the two candidates
    disagree, z_a = NormalDist().inv_cdf(1 - alpha / 2) and
    z_b = NormalDist().inv_cdf(power).

    A paired difference can never exceed the disagreement rate, and at
    delta == psi every disagreement goes one way, so the formula applies only
    when 0 < delta < psi. Raise ValueError otherwise.
    """
    # TODO(L7.1): implement using the definition in the docstring.
    raise NotImplementedError("paired_sample_size")

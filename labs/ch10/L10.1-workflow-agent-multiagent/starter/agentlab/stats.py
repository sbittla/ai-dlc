"""Statistics for comparing designs on the same tasks (provided; copied from Lab 7.1's reference solution)."""

from __future__ import annotations

import math
import random
from statistics import NormalDist


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (Chapter 2)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar test on discordant counts (Chapter 7, Equation 7.2)."""
    if b < 0 or c < 0:
        raise ValueError("counts must be non-negative")
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def cluster_bootstrap(clusters: list[list[float]], n_resamples: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Mean per-task difference and its 95% interval, resampling whole families (Chapter 7)."""
    if not clusters or not any(clusters):
        raise ValueError("no differences")
    rng = random.Random(seed)
    sums = [sum(c) for c in clusters]
    counts = [len(c) for c in clusters]
    k = len(clusters)
    means = []
    for _ in range(n_resamples):
        idx = [rng.randrange(k) for _ in range(k)]
        means.append(sum(sums[i] for i in idx) / sum(counts[i] for i in idx))
    means.sort()
    return sum(sums) / sum(counts), means[int(0.025 * n_resamples)], means[int(0.975 * n_resamples) - 1]


def paired_sample_size(discordant_rate: float, delta: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Tasks needed to detect a paired difference `delta` (Connor, 1987; Chapter 7, Equation 7.3)."""
    if not 0 < delta < discordant_rate:
        raise ValueError("need 0 < delta < discordant_rate")
    z_a = NormalDist().inv_cdf(1 - alpha / 2)
    z_b = NormalDist().inv_cdf(power)
    n = (z_a * math.sqrt(discordant_rate) + z_b * math.sqrt(discordant_rate - delta * delta)) ** 2 / delta ** 2
    return math.ceil(n)


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile: the smallest value with at least q of the values at or below it."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]

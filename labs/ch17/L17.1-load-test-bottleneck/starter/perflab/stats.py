"""Percentiles of one run, and the spread of a statistic across repeated runs (reference solution)."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Two-sided 95% critical values of Student's t for 1-10 degrees of freedom (standard tables).
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def percentile(sorted_values: list, p: float):
    """TODO 2a. Nearest-rank percentile of values already sorted ascending.

    The p-th percentile is the value at rank ceil(p / 100 x n) (1-based), and at least rank 1: the smallest
    value with at least p% of the values at or below it. It is always one of the measured values; nothing is
    interpolated. Raise ValueError for an empty list or p outside 0-100.
    """
    raise NotImplementedError("TODO 2")


@dataclass(frozen=True)
class Summary:
    n: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def summarize(latencies_us: list[int]) -> Summary:
    """TODO 2b. Summary of one run's latencies (microseconds in, milliseconds out, not rounded)."""
    raise NotImplementedError("TODO 2")


def mean_interval(values: list[float]) -> tuple[float, float, float]:
    """TODO 2c. Mean of a statistic over repeated runs and its 95% t-interval: (mean, low, high).

    mean +- T95[n - 1] x s / sqrt(n), with s the sample standard deviation (divisor n - 1). The runs are
    treated as independent draws of the same measurement; that is only as true as the runs were controlled
    (same machine, same schedule, interleaved configurations). Raise ValueError for fewer than 2 values or
    more than 11.
    """
    raise NotImplementedError("TODO 2")

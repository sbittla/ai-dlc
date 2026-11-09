"""Paired comparison of two designs on the same tasks, and Chapter 7's gate rule applied to it.

Each design ran every task three times with the same draws, so the comparison is paired by task. Tasks of
one family share files and shape, so they are not independent evidence: the interval resamples families
(a cluster bootstrap), and McNemar's exact test is reported beside it on each task's majority outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from .evaluate import by_design, majority
from .stats import cluster_bootstrap, mcnemar_exact


@dataclass(frozen=True)
class Comparison:
    candidate: str
    reference: str
    metric: str
    diff: float        # mean over tasks of (candidate share - reference share), in points
    low: float         # 95% cluster-bootstrap interval, in points
    high: float
    b: int             # tasks the reference got right (by majority) and the candidate got wrong
    c: int             # tasks the candidate got right and the reference got wrong
    p: float           # exact McNemar p on b and c
    cost_change: float  # candidate's mean cost per run relative to the reference's (-0.25 is 25% cheaper)


def shares(records, metric: str) -> dict[str, float]:
    """Each task's share of runs for which `metric` (a RunRecord attribute) is true."""
    runs: dict[str, list[bool]] = {}
    for r in records:
        runs.setdefault(r.task_id, []).append(bool(getattr(r, metric)))
    return {t: sum(v) / len(v) for t, v in runs.items()}


def compare(records, candidate: str, reference: str, metric: str = "success") -> Comparison:
    """Compare `candidate` with `reference` on `metric`.

    1. Per task, the share of runs with the metric true, for each design (`shares`). The per-task
       difference is candidate share minus reference share, times 100 (points).
    2. Group the differences by the task's family, in order of first appearance in `records`, and
       compute cluster_bootstrap(groups) with its default resamples and seed: (diff, low, high).
    3. On each task's majority outcome of the metric over its runs (more than half true), count
       b = reference true and candidate false, c = candidate true and reference false;
       p = mcnemar_exact(b, c).
    4. cost_change = candidate's mean usd per run / reference's mean usd per run - 1.
    """
    cand, ref = by_design(records, candidate), by_design(records, reference)
    sc, sr = shares(cand, metric), shares(ref, metric)
    family = {r.task_id: r.family for r in ref}
    groups: dict[str, list[float]] = {}
    for task in sr:
        groups.setdefault(family[task], []).append(100 * (sc[task] - sr[task]))
    diff, low, high = cluster_bootstrap(list(groups.values()))
    mc = {t: v > 0.5 for t, v in sc.items()}
    mr = {t: v > 0.5 for t, v in sr.items()}
    b = sum(mr[t] and not mc[t] for t in mr)
    c = sum(mc[t] and not mr[t] for t in mr)
    cost_c = sum(r.usd for r in cand) / len(cand)
    cost_r = sum(r.usd for r in ref) / len(ref)
    return Comparison(candidate, reference, metric, diff, low, high, b, c, mcnemar_exact(b, c), cost_c / cost_r - 1)


def gate(comp: Comparison, policy: dict) -> str:
    """Chapter 7's regression rule (Figure 7.2) on a success comparison.

    FAIL if the lower bound is below -margin; else PASS if the candidate cuts cost per run by at least
    benefit_cost_reduction; else FAIL if the upper bound is below 0; else PASS.
    """
    margin, benefit = policy["margin_points"], policy["benefit_cost_reduction"]
    if comp.low < -margin:
        return "FAIL: a loss larger than the margin cannot be ruled out"
    if comp.cost_change <= -benefit:
        return "PASS: non-inferior within the margin, and cheaper"
    if comp.high < 0:
        return "FAIL: worse beyond noise"
    return "PASS: improvement" if comp.low > 0 else "PASS: no clear change"


def check_majority_counts(records, design: str) -> int:
    """Tasks a design gets right by majority (used by the report and the tests)."""
    return sum(majority(by_design(records, design)).values())

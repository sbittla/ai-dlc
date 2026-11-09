"""Three routing configurations on Lab 7.1's held-out tickets: quality, latency and cost per correct triage.

Quality is judged as Chapter 7 judges it: on the 200 held-out tickets, three runs each, with paired
comparisons against the baseline (a cluster bootstrap over ticket families, and McNemar's exact test on each
ticket's majority outcome). The difference here is that a run is a production triage under Relay's worker
rules (production.py), not one call: a ticket the worker gives up on gets no suggestion, and counts as wrong.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from .dataset import split
from .production import CONFIGS, Outcome, tickets, triage
from .router import Router, choose_threshold, out_of_fold_scores, train
from .stats import cluster_bootstrap, mcnemar_exact, wilson_interval

RUNS = 3


@lru_cache(maxsize=1)
def router() -> tuple[Router, float]:
    """Chapter 7's router, trained on dev; threshold from out-of-fold dev scores at the configured recall."""
    dev = split(list(tickets()), "dev")
    scores = out_of_fold_scores(dev)
    threshold = choose_threshold(scores, [t["difficulty"] == "hard" for t in dev],
                                 CONFIGS["configs"]["routed"]["router_min_recall"])
    return train(dev), threshold


def route_for(config: str, ticket: dict) -> tuple[str, dict]:
    cfg = CONFIGS["configs"][config]
    if "hard" in cfg:
        r, threshold = router()
        if r.score(ticket["text"]) >= threshold:
            return "hard", cfg["hard"]
    return "default", cfg["default"]


@lru_cache(maxsize=8)
def run_config(config: str, split_name: str = "heldout") -> tuple[Outcome, ...]:
    out = []
    for t in split(list(tickets()), split_name):
        name, route = route_for(config, t)
        for run in range(1, RUNS + 1):
            out.append(triage(t, run, route, name))
    return tuple(out)


def percentile(values: list[float], p: float) -> float:
    """Nearest rank, as Lab 17.1 computes it."""
    v = sorted(values)
    return v[max(1, math.ceil(p / 100 * len(v))) - 1]


@dataclass(frozen=True)
class Summary:
    config: str
    runs: int
    correct: int
    wrong: int
    needs_human: int
    quality: float                 # correct / runs
    quality_low: float
    quality_high: float
    first_call_accuracy: float     # what the offline gate measured
    wrong_share_of_suggestions: float
    calls_per_run: float
    timeouts: int
    usd_per_call: float
    usd_per_run: float
    usd_per_correct: float
    call_p50_s: float
    call_p95_s: float
    ttft_p95_s: float
    suggestion_p50_s: float
    suggestion_p95_s: float
    hard_route_share: float


def summarize(config: str, outcomes: tuple[Outcome, ...]) -> Summary:
    """TODO 2a. Summarize one configuration's outcomes.

    quality = correct runs / all runs, with its Wilson interval; first_call_accuracy = share of runs whose first
    call was correct; wrong_share_of_suggestions = wrong / (correct + wrong). usd_per_call = all cost / all
    calls; usd_per_run = all cost / runs; usd_per_correct = all cost / correct runs. Latency percentiles are
    nearest-rank: call_p50_s and call_p95_s over every call's latency, ttft_p95_s over every call's time to first
    token, suggestion_p50_s and suggestion_p95_s over the runs that ended in a suggestion (correct or wrong).
    hard_route_share = share of runs on the "hard" route.
    """
    n = len(outcomes)
    correct = sum(o.result == "correct" for o in outcomes)
    wrong = sum(o.result == "wrong" for o in outcomes)
    calls = sum(o.calls for o in outcomes)
    usd = sum(o.usd for o in outcomes)
    lo, hi = wilson_interval(correct, n)
    lats = [x for o in outcomes for x in o.call_latencies]
    ttfts = [x for o in outcomes for x in o.ttfts]
    waits = [o.seconds for o in outcomes if o.result != "needs_human"]
    return Summary(config, n, correct, wrong, n - correct - wrong, correct / n, lo, hi,
                   sum(o.first_call_correct for o in outcomes) / n, wrong / (correct + wrong), calls / n,
                   sum(o.timeouts for o in outcomes), usd / calls, usd / n, usd / correct,
                   percentile(lats, 50), percentile(lats, 95), percentile(ttfts, 95),
                   percentile(waits, 50), percentile(waits, 95), sum(o.route == "hard" for o in outcomes) / n)


@dataclass(frozen=True)
class Paired:
    config: str
    diff_points: float
    low: float
    high: float
    worse: int    # tickets correct by majority under the baseline and not under the candidate
    better: int
    p_value: float


def paired(candidate: str, baseline: str | None = None, split_name: str = "heldout") -> Paired:
    """TODO 2b. The candidate against the baseline on the same tickets, as Chapter 7 compares them.

    Per ticket, the share of its runs that were correct, for each configuration; the difference (candidate
    minus baseline), clustered by the ticket's family, goes to stats.cluster_bootstrap (default resamples and
    seed). Report it in percentage points. worse and better count tickets whose majority outcome (correct in
    more than half of the runs) differs; p_value is mcnemar_exact(worse, better).
    """
    baseline = baseline or CONFIGS["baseline"]
    fam = {t["id"]: t["family"] for t in tickets()}

    def shares(outcomes):
        runs: dict[str, list[bool]] = defaultdict(list)
        for o in outcomes:
            runs[o.ticket_id].append(o.result == "correct")
        return {k: sum(v) / len(v) for k, v in runs.items()}

    a, b = shares(run_config(baseline, split_name)), shares(run_config(candidate, split_name))
    clusters: dict[str, list[float]] = defaultdict(list)
    for tid in sorted(a):
        clusters[fam[tid]].append(b[tid] - a[tid])
    mean, low, high = cluster_bootstrap([clusters[f] for f in sorted(clusters)])
    worse = sum(a[t] > 0.5 and not b[t] > 0.5 for t in a)
    better = sum(b[t] > 0.5 and not a[t] > 0.5 for t in a)
    return Paired(candidate, 100 * mean, 100 * low, 100 * high, worse, better, mcnemar_exact(worse, better))


def table(split_name: str = "heldout") -> list[Summary]:
    return [summarize(c, run_config(c, split_name)) for c in ("large", "reasoner", "routed")]


@dataclass(frozen=True)
class Offline:
    config: str
    accuracy: float           # first calls correct / runs
    usd_per_correct: float    # first calls' cost / first calls correct
    paired: Paired


def offline(candidate: str, baseline: str | None = None) -> Offline:
    """What Lab 7.1's gate would have reported: first calls only, no clock, no retries (provided)."""
    baseline = baseline or CONFIGS["baseline"]
    fam = {t["id"]: t["family"] for t in tickets()}

    def shares(outcomes):
        runs: dict[str, list[bool]] = defaultdict(list)
        for o in outcomes:
            runs[o.ticket_id].append(o.first_call_correct)
        return {k: sum(v) / len(v) for k, v in runs.items()}

    outs = run_config(candidate)
    a, b = shares(run_config(baseline)), shares(outs)
    clusters: dict[str, list[float]] = defaultdict(list)
    for tid in sorted(a):
        clusters[fam[tid]].append(b[tid] - a[tid])
    mean, low, high = cluster_bootstrap([clusters[f] for f in sorted(clusters)])
    worse = sum(a[t] > 0.5 and not b[t] > 0.5 for t in a)
    better = sum(b[t] > 0.5 and not a[t] > 0.5 for t in a)
    k = sum(o.first_call_correct for o in outs)
    return Offline(candidate, k / len(outs), sum(o.first_call_usd for o in outs) / k,
                   Paired(candidate, 100 * mean, 100 * low, 100 * high, worse, better, mcnemar_exact(worse, better)))

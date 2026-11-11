"""The pre-registered readout of the pilot (Chapter 20, Section 20.5 and the worked example).

Tasks were randomized within the two pilot teams, so every comparison is made within engineer: each engineer's
agent tasks against the same engineer's control tasks, then averaged over engineers. The registered test is a
paired t-test on the engineers' differences, with a t interval (15 engineers, 14 degrees of freedom). The exact
sign test over the same differences is the registered robustness check (the binomial computation of Chapter 7's
exact McNemar test). A percentile cluster bootstrap over engineers (Chapter 7) is printed beside the t interval as
a check; with only 15 clusters it runs narrower than the t interval, which is why it is not the registered one.
"""

from __future__ import annotations

import math
import random

from .stats import binom_two_sided, percentile, t_cdf, t_quantile

BOOT_SEED = 20270615
RESAMPLES = 2000


def pilot_rows(rows: list[dict], teams: tuple[str, ...] = ("integrations", "analytics")) -> list[dict]:
    return [r for r in rows if r["period"] == "pilot" and r["team"] in teams and r["arm"] in ("agent", "control")]


def _by_engineer(rows: list[dict], value) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        out.setdefault(r["engineer"], {"agent": [], "control": []})[r["arm"]].append(value(r))
    return {e: v for e, v in out.items() if v["agent"] and v["control"]}


def paired_t(diffs: list[float], alpha: float = 0.05) -> tuple[float, float, float, float]:
    """Paired t-test on engineers' differences: return (mean, low, high, p).

    mean is the mean of diffs; the interval is mean -/+ t_quantile(1 - alpha / 2, k - 1) * s / sqrt(k), where s is
    the sample standard deviation (divisor k - 1); p is the two-sided p-value 2 * (1 - t_cdf(|mean| / (s /
    sqrt(k)), k - 1)). Needs at least two differences; if s is 0, return (mean, mean, mean, 0.0) when mean is not 0
    and (0.0, 0.0, 0.0, 1.0) when it is.
    """
    raise NotImplementedError("TODO 3: implement paired_t")


def _summarise(diffs: list[float], transform, seed: int) -> dict:
    """Paired t estimate and interval, sign test, and a percentile cluster bootstrap as a check (provided)."""
    rng = random.Random(seed)
    k = len(diffs)
    m, lo, hi, p = paired_t(diffs)
    boots = []
    for _ in range(RESAMPLES):
        sample = [diffs[rng.randrange(k)] for _ in range(k)]
        boots.append(sum(sample) / k)
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    return {"estimate": transform(m), "low": transform(lo), "high": transform(hi), "t_test_p": p, "engineers": k,
            "positive": pos, "negative": neg, "sign_test_p": binom_two_sided(pos, neg),
            "boot_low": transform(percentile(boots, 0.025)), "boot_high": transform(percentile(boots, 0.975))}


def within_engineer_log_ratio(rows: list[dict], outcome: str, seed: int = BOOT_SEED) -> dict:
    """Ratio of geometric means, agent over control, estimated within engineer (provided).

    For each engineer with at least one change in each arm: d = mean(log outcome | agent) - mean(log outcome |
    control). The estimate is exp(mean of d); the interval is the paired t interval, exponentiated.
    """
    groups = _by_engineer(rows, lambda r: math.log(r[outcome]))
    diffs = [sum(v["agent"]) / len(v["agent"]) - sum(v["control"]) / len(v["control"])
             for _e, v in sorted(groups.items())]
    return _summarise(diffs, math.exp, seed)


def within_engineer_hours_saved(rows: list[dict], outcome: str, seed: int = BOOT_SEED) -> dict:
    """Mean hours per change, control minus agent, within engineer (positive = agents save time). Provided."""
    groups = _by_engineer(rows, lambda r: r[outcome])
    diffs = [sum(v["control"]) / len(v["control"]) - sum(v["agent"]) / len(v["agent"])
             for _e, v in sorted(groups.items())]
    return _summarise(diffs, lambda x: x, seed)


def net_hours_saved(rows: list[dict], seed: int = BOOT_SEED) -> dict:
    """Author hours saved minus review hours added per change, within engineer. Provided."""
    groups = _by_engineer(rows, lambda r: r["author_hours"] + r["review_hours"])
    diffs = [sum(v["control"]) / len(v["control"]) - sum(v["agent"]) / len(v["agent"])
             for _e, v in sorted(groups.items())]
    return _summarise(diffs, lambda x: x, seed)


def failure_rates(rows: list[dict], seed: int = BOOT_SEED) -> dict:
    """Change fail rate per arm, and the within-engineer difference (agent minus control, points) with its paired t
    interval, as for the other outcomes. Provided."""
    groups = _by_engineer(rows, lambda r: 1.0 if r["failed"] else 0.0)
    diffs = [100 * (sum(v["agent"]) / len(v["agent"]) - sum(v["control"]) / len(v["control"]))
             for _e, v in sorted(groups.items())]
    summary = _summarise(diffs, lambda x: x, seed)
    a = [r for r in rows if r["arm"] == "agent"]
    c = [r for r in rows if r["arm"] == "control"]
    return {"agent_failed": sum(r["failed"] for r in a), "agent_n": len(a),
            "control_failed": sum(r["failed"] for r in c), "control_n": len(c),
            "difference_points": summary["estimate"], "low": summary["low"], "high": summary["high"],
            "t_test_p": summary["t_test_p"]}


def team_medians(rows: list[dict], outcome: str) -> dict[tuple[str, str], float]:
    """Median of an outcome per (period, team), for the team-level guardrails (descriptive only). Provided."""
    out: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        out.setdefault((r["period"], r["team"]), []).append(r[outcome])
    return {k: percentile(v, 0.5) for k, v in sorted(out.items())}


def skills_mcnemar(skills: dict, teams: tuple[str, ...]) -> dict:
    """Exact McNemar test on the unassisted exercise, before against after, for the given teams. Provided."""
    rows = [r for r in skills["results"] if r["team"] in teams]
    b = sum(1 for r in rows if r["before"] and not r["after"])   # passed before, failed after
    c = sum(1 for r in rows if not r["before"] and r["after"])   # failed before, passed after
    return {"engineers": len(rows), "pass_before": sum(r["before"] for r in rows),
            "pass_after": sum(r["after"] for r in rows), "b": b, "c": c, "p": binom_two_sided(b, c)}

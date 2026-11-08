"""Delivery and value-stream metrics for Relay (reference solution).

Every function documents its exact definition. When two teams disagree about
a number, the disagreement is almost always about the definition, so the
definitions here are part of the deliverable, not decoration.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from .data import Change, Dataset, Deployment, MonthlyCost

HOURS = 3600.0


def _hours(delta) -> float:
    return delta.total_seconds() / HOURS


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it.

    Nearest-rank is used because it always returns an observed value, which
    makes it easy to explain ("90% of changes shipped within X hours").
    """
    if not values:
        raise ValueError("percentile of empty list")
    if not 0 < p <= 100:
        raise ValueError("p must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered))
    return ordered[rank - 1]


@dataclass(frozen=True)
class LeadTime:
    median_h: float
    p90_h: float
    n: int


def change_lead_time(changes: list[Change]) -> LeadTime:
    """Change lead time: first commit to running in production, in hours.

    Includes every deployed change (feature and hotfix), reverted or not,
    because a reverted change still travelled the whole pipeline.
    """
    hours = [_hours(c.deployed_at - c.first_commit_at) for c in changes]
    return LeadTime(median_h=statistics.median(hours), p90_h=percentile(hours, 90), n=len(hours))


def deployment_frequency_per_week(deployments: list[Deployment], weeks: float) -> float:
    """Deployments of any kind (planned and hotfix) per week."""
    if weeks <= 0:
        raise ValueError("weeks must be positive")
    return len(deployments) / weeks


def change_fail_rate(deployments: list[Deployment]) -> float:
    """Share of deployments that failed in production and needed remediation."""
    if not deployments:
        raise ValueError("no deployments")
    return sum(d.failed for d in deployments) / len(deployments)


def recovery_time_hours(deployments: list[Deployment]) -> float:
    """Failed deployment recovery time: median hours from a failed deploy to service restored."""
    hours = [_hours(d.restored_at - d.deployed_at) for d in deployments if d.failed and d.restored_at]
    if not hours:
        raise ValueError("no failed deployments with a recovery time")
    return statistics.median(hours)


def rework_rate(deployments: list[Deployment]) -> float:
    """Share of deployments that were unplanned fixes for production problems (kind == "hotfix")."""
    if not deployments:
        raise ValueError("no deployments")
    return sum(d.kind == "hotfix" for d in deployments) / len(deployments)


STAGES = ("coding", "review_wait", "review", "merge_wait", "deploy_wait")
ACTIVE_STAGES = ("coding", "review")


def stage_hours(c: Change) -> dict[str, float]:
    """Hours each change spent in each value-stream stage."""
    return {
        "coding": _hours(c.pr_opened_at - c.first_commit_at),
        "review_wait": _hours(c.first_review_at - c.pr_opened_at),
        "review": _hours(c.approved_at - c.first_review_at),
        "merge_wait": _hours(c.merged_at - c.approved_at),
        "deploy_wait": _hours(c.deployed_at - c.merged_at),
    }


@dataclass(frozen=True)
class FlowBreakdown:
    median_stage_h: dict[str, float]
    flow_efficiency: float  # share of total elapsed time spent in active stages


def flow_breakdown(changes: list[Change]) -> FlowBreakdown:
    """Median hours per stage, and flow efficiency.

    Flow efficiency = total active hours / total elapsed hours, summed over all
    changes (not a median of ratios), so long-running changes weigh more.
    Only feature changes are included: hotfixes skip the normal queues and
    would flatter the picture.
    """
    features = [c for c in changes if c.kind == "feature"]
    if not features:
        raise ValueError("no feature changes")
    per_change = [stage_hours(c) for c in features]
    medians = {s: statistics.median(pc[s] for pc in per_change) for s in STAGES}
    active = sum(pc[s] for pc in per_change for s in ACTIVE_STAGES)
    total = sum(pc[s] for pc in per_change for s in STAGES)
    return FlowBreakdown(median_stage_h=medians, flow_efficiency=active / total)


def accepted_changes(changes: list[Change]) -> list[Change]:
    """Feature changes that reached production and were not later reverted."""
    return [c for c in changes if c.kind == "feature" and not c.reverted]


def cost_per_accepted_change(changes: list[Change], costs: list[MonthlyCost]) -> float:
    """Total delivery cost in the period divided by accepted changes.

    Cost includes engineering time, AI tooling and CI/cloud. This is a cost
    per *change*, not per unit of value: Chapter 1 explains why it can fall
    while outcomes get worse.
    """
    accepted = accepted_changes(changes)
    if not accepted:
        raise ValueError("no accepted changes")
    return sum(c.total_usd for c in costs) / len(accepted)


@dataclass(frozen=True)
class QueueStats:
    mean_review_wait_h: float
    p90_review_wait_h: float
    arrivals_per_hour: float
    avg_waiting: float  # Little's Law: L = lambda * W


def littles_law(arrival_rate: float, mean_time_in_queue: float) -> float:
    """Average number of items in a queue: L = lambda * W (same time units for both)."""
    return arrival_rate * mean_time_in_queue


def review_queue(changes: list[Change], weeks: float) -> QueueStats:
    """Review-wait statistics for feature changes, and the average queue length.

    Arrival rate is feature changes per calendar hour over the period. Little's
    Law needs the *mean* wait, not the median.
    """
    waits = [stage_hours(c)["review_wait"] for c in changes if c.kind == "feature"]
    rate = len(waits) / (weeks * 7 * 24)
    mean_wait = statistics.mean(waits)
    return QueueStats(mean_wait, percentile(waits, 90), rate, littles_law(rate, mean_wait))


def review_load_hours(changes: list[Change]) -> float:
    """Total elapsed hours feature changes spent in the review stage (first review to approval)."""
    return sum(stage_hours(c)["review"] for c in changes if c.kind == "feature")


def lines_changed_total(changes: list[Change]) -> int:
    """Total lines changed across feature changes: a rough proxy for review volume."""
    return sum(c.lines_changed for c in changes if c.kind == "feature")


def recovery_time_mean_hours(deployments: list[Deployment]) -> float:
    """Mean hours from failed deployment to restored (compare with the median)."""
    hours = [_hours(d.restored_at - d.deployed_at) for d in deployments if d.failed and d.restored_at]
    return statistics.mean(hours)


def next_weekday_train(t: datetime, hour: int = 15) -> datetime:
    """The first weekday deploy train at `hour`:00 at or after time t."""
    candidate = t.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate < t:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:  # Saturday=5, Sunday=6
        candidate += timedelta(days=1)
    return candidate


def daily_deploy_counterfactual(changes: list[Change], hour: int = 15) -> LeadTime:
    """Feature-change lead time if every merged change shipped on the next weekday train.

    A what-if, not a forecast: it assumes the same merge times and that a
    daily train would not change review behaviour or failure rates.
    """
    hours = [_hours(next_weekday_train(c.merged_at, hour) - c.first_commit_at) for c in changes if c.kind == "feature"]
    return LeadTime(median_h=statistics.median(hours), p90_h=percentile(hours, 90), n=len(hours))


def ai_assisted_share(changes: list[Change]) -> float:
    """Share of feature changes marked as AI-assisted (a self-reported flag; see Chapter 1)."""
    features = [c for c in changes if c.kind == "feature"]
    return sum(c.ai_assisted for c in features) / len(features)


def median_change_size(changes: list[Change]) -> float:
    """Median lines changed per feature change."""
    return statistics.median(c.lines_changed for c in changes if c.kind == "feature")


@dataclass(frozen=True)
class Baseline:
    period: str
    feature_changes: int
    deployments: int
    lead_time: LeadTime
    deploys_per_week: float
    change_fail_rate: float
    recovery_time_h: float
    rework_rate: float
    flow: FlowBreakdown
    accepted_changes: int
    cost_per_accepted_change_usd: float
    ai_assisted_share: float
    median_change_lines: float
    feature_lead_time: LeadTime
    failed_deployments: int
    hotfix_deployments: int
    reverted_changes: int
    recovery_time_mean_h: float
    queue: QueueStats
    review_load_h: float
    lines_changed: int
    daily_deploy_lead_time: LeadTime


def baseline(ds: Dataset, period: str) -> Baseline:
    """Compute every baseline metric for one period."""
    return Baseline(
        period=period,
        feature_changes=sum(c.kind == "feature" for c in ds.changes),
        deployments=len(ds.deployments),
        lead_time=change_lead_time(ds.changes),
        deploys_per_week=deployment_frequency_per_week(ds.deployments, ds.weeks),
        change_fail_rate=change_fail_rate(ds.deployments),
        recovery_time_h=recovery_time_hours(ds.deployments),
        rework_rate=rework_rate(ds.deployments),
        flow=flow_breakdown(ds.changes),
        accepted_changes=len(accepted_changes(ds.changes)),
        cost_per_accepted_change_usd=cost_per_accepted_change(ds.changes, ds.costs),
        ai_assisted_share=ai_assisted_share(ds.changes),
        median_change_lines=median_change_size(ds.changes),
        feature_lead_time=change_lead_time([c for c in ds.changes if c.kind == "feature"]),
        failed_deployments=sum(d.failed for d in ds.deployments),
        hotfix_deployments=sum(d.kind == "hotfix" for d in ds.deployments),
        reverted_changes=sum(c.reverted for c in ds.changes),
        recovery_time_mean_h=recovery_time_mean_hours(ds.deployments),
        queue=review_queue(ds.changes, ds.weeks),
        review_load_h=review_load_hours(ds.changes),
        lines_changed=lines_changed_total(ds.changes),
        daily_deploy_lead_time=daily_deploy_counterfactual(ds.changes),
    )


@dataclass(frozen=True)
class MonthStability:
    month: str
    deployments: int
    failed: int
    hotfixes: int

    @property
    def change_fail_rate(self) -> float:
        return self.failed / self.deployments

    @property
    def rework_rate(self) -> float:
        return self.hotfixes / self.deployments


def monthly_stability(deployments: list[Deployment]) -> list[MonthStability]:
    """Change fail rate and rework rate per calendar month.

    Monthly windows hold only 6-10 deployments here, so one failure moves the
    rate by 10 percentage points or more. Use this to choose a guardrail
    window that does not raise false alarms.
    """
    months: dict[str, list[Deployment]] = {}
    for d in deployments:
        months.setdefault(d.deployed_at.strftime("%Y-%m"), []).append(d)
    return [
        MonthStability(m, len(ds), sum(d.failed for d in ds), sum(d.kind == "hotfix" for d in ds))
        for m, ds in sorted(months.items())
    ]


def rolling_stability(deployments: list[Deployment], months: int = 3) -> list[MonthStability]:
    """Change fail rate and rework rate over rolling windows of `months` calendar months.

    Each result is labelled with its first and last month ("2026-02..2026-04").
    Only complete windows are returned.
    """
    monthly = monthly_stability(deployments)
    out = []
    for i in range(len(monthly) - months + 1):
        win = monthly[i:i + months]
        out.append(MonthStability(
            f"{win[0].month}..{win[-1].month}",
            sum(m.deployments for m in win), sum(m.failed for m in win), sum(m.hotfixes for m in win),
        ))
    return out

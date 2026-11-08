"""Load Relay delivery data and slice it by period.

This module is provided complete in both starter/ and solution/. Learners
implement the metrics in metrics.py, not the loading code.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TS = "%Y-%m-%dT%H:%M"

# Quarter boundaries are [start, end): start inclusive, end exclusive.
PERIODS: dict[str, tuple[datetime, datetime]] = {
    "2026Q1": (datetime(2026, 1, 1), datetime(2026, 4, 1)),
    "2026Q2": (datetime(2026, 4, 1), datetime(2026, 7, 1)),
}


@dataclass(frozen=True)
class Change:
    change_id: str
    kind: str  # "feature" or "hotfix"
    first_commit_at: datetime
    pr_opened_at: datetime
    first_review_at: datetime
    approved_at: datetime
    merged_at: datetime
    deployed_at: datetime
    deploy_id: str
    lines_changed: int
    ai_assisted: bool
    reverted: bool


@dataclass(frozen=True)
class Deployment:
    deploy_id: str
    deployed_at: datetime
    kind: str  # "planned" or "hotfix"
    failed: bool
    restored_at: datetime | None


@dataclass(frozen=True)
class MonthlyCost:
    month: str  # "YYYY-MM"
    engineering_usd: float
    ai_tooling_usd: float
    ci_cloud_usd: float

    @property
    def total_usd(self) -> float:
        return self.engineering_usd + self.ai_tooling_usd + self.ci_cloud_usd


@dataclass(frozen=True)
class Dataset:
    changes: list[Change]
    deployments: list[Deployment]
    costs: list[MonthlyCost]
    weeks: float  # length of the period in weeks, used for frequency metrics


def _ts(value: str) -> datetime:
    return datetime.strptime(value, TS)


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def load(data_dir: Path) -> Dataset:
    """Load all three CSV files from `data_dir`."""
    with (data_dir / "changes.csv").open(encoding="utf-8") as f:
        changes = [
            Change(
                change_id=r["change_id"],
                kind=r["kind"],
                first_commit_at=_ts(r["first_commit_at"]),
                pr_opened_at=_ts(r["pr_opened_at"]),
                first_review_at=_ts(r["first_review_at"]),
                approved_at=_ts(r["approved_at"]),
                merged_at=_ts(r["merged_at"]),
                deployed_at=_ts(r["deployed_at"]),
                deploy_id=r["deploy_id"],
                lines_changed=int(r["lines_changed"]),
                ai_assisted=_bool(r["ai_assisted"]),
                reverted=_bool(r["reverted"]),
            )
            for r in csv.DictReader(f)
        ]
    with (data_dir / "deployments.csv").open(encoding="utf-8") as f:
        deployments = [
            Deployment(
                deploy_id=r["deploy_id"],
                deployed_at=_ts(r["deployed_at"]),
                kind=r["kind"],
                failed=_bool(r["failed"]),
                restored_at=_ts(r["restored_at"]) if r["restored_at"] else None,
            )
            for r in csv.DictReader(f)
        ]
    with (data_dir / "costs.csv").open(encoding="utf-8") as f:
        costs = [
            MonthlyCost(
                month=r["month"],
                engineering_usd=float(r["engineering_usd"]),
                ai_tooling_usd=float(r["ai_tooling_usd"]),
                ci_cloud_usd=float(r["ci_cloud_usd"]),
            )
            for r in csv.DictReader(f)
        ]
    return Dataset(changes, deployments, costs, weeks=0.0)


def period_weeks(period: str) -> float:
    """Calendar length of a period in weeks (2026Q1 is 90 days, about 12.86 weeks)."""
    start, end = PERIODS[period]
    return (end - start).days / 7


def for_period(ds: Dataset, period: str) -> Dataset:
    """Return only the records whose deployment (or cost month) falls in `period`.

    Changes and deployments are assigned to the period in which they were
    deployed, because that is when they started delivering (or failing to
    deliver) value. `weeks` is the calendar length of the period, used for
    per-week rates.
    """
    start, end = PERIODS[period]
    weeks = period_weeks(period)
    months = {f"{start.year}-{m:02d}" for m in range(start.month, start.month + 3)}
    return Dataset(
        changes=[c for c in ds.changes if start <= c.deployed_at < end],
        deployments=[d for d in ds.deployments if start <= d.deployed_at < end],
        costs=[c for c in ds.costs if c.month in months],
        weeks=weeks,
    )

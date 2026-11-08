"""Print a Markdown baseline report comparing delivery periods.

Usage (from the starter/ or solution/ folder):

    python -m vsm.report --data ../data --period 2026Q1 --compare 2026Q2
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import data, metrics


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render(rows: list[metrics.Baseline]) -> str:
    header = "| Metric | " + " | ".join(b.period for b in rows) + " |"
    sep = "| --- | " + " | ".join("---:" for _ in rows) + " |"
    lines = [header, sep]

    def row(name: str, fn) -> None:
        lines.append(f"| {name} | " + " | ".join(fn(b) for b in rows) + " |")

    row("Feature changes deployed", lambda b: str(b.feature_changes))
    row("Deployments (planned + hotfix)", lambda b: str(b.deployments))
    row("Failed deployments", lambda b: str(b.failed_deployments))
    row("Hotfix deployments", lambda b: str(b.hotfix_deployments))
    row("Reverted changes", lambda b: str(b.reverted_changes))
    row("Deployments per week", lambda b: f"{b.deploys_per_week:.2f}")
    row("Change lead time, median (h), all changes", lambda b: f"{b.lead_time.median_h:.1f}")
    row("Change lead time, p90 (h), all changes", lambda b: f"{b.lead_time.p90_h:.1f}")
    row("Change lead time, median (h), feature changes", lambda b: f"{b.feature_lead_time.median_h:.1f}")
    row("Change fail rate", lambda b: _pct(b.change_fail_rate))
    row("Failed deployment recovery time, median (h)", lambda b: f"{b.recovery_time_h:.1f}")
    row("Failed deployment recovery time, mean (h)", lambda b: f"{b.recovery_time_mean_h:.1f}")
    row("Rework rate (hotfix share of deployments)", lambda b: _pct(b.rework_rate))
    for stage in metrics.STAGES:
        row(f"Median {stage.replace('_', ' ')} (h)", lambda b, s=stage: f"{b.flow.median_stage_h[s]:.1f}")
    row("Flow efficiency", lambda b: _pct(b.flow.flow_efficiency))
    row("Accepted changes (not reverted)", lambda b: str(b.accepted_changes))
    row("Total delivery cost (USD)", lambda b: f"{b.cost_per_accepted_change_usd * b.accepted_changes:,.0f}")
    row("Cost per accepted change (USD)", lambda b: f"{b.cost_per_accepted_change_usd:,.0f}")
    row("Review wait, mean (h)", lambda b: f"{b.queue.mean_review_wait_h:.1f}")
    row("Review wait, p90 (h)", lambda b: f"{b.queue.p90_review_wait_h:.1f}")
    row("Changes waiting for review, average (Little's Law)", lambda b: f"{b.queue.avg_waiting:.2f}")
    row("Review-stage hours, total", lambda b: f"{b.review_load_h:,.0f}")
    row("Lines changed, total (feature changes)", lambda b: f"{b.lines_changed:,}")
    row("Median change size (lines)", lambda b: f"{b.median_change_lines:.1f}")
    row("AI-assisted share of feature changes", lambda b: _pct(b.ai_assisted_share))
    row("What-if: daily deploys, feature lead time median (h)", lambda b: f"{b.daily_deploy_lead_time.median_h:.1f}")
    return "\n".join(lines)


def render_monthly(months: list[metrics.MonthStability]) -> str:
    lines = ["| Month | Deployments | Failed | Hotfixes | Change fail rate | Rework rate |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for m in months:
        lines.append(f"| {m.month} | {m.deployments} | {m.failed} | {m.hotfixes} | "
                     f"{_pct(m.change_fail_rate)} | {_pct(m.rework_rate)} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay delivery baseline report")
    parser.add_argument("--data", type=Path, required=True, help="folder containing the CSV files")
    parser.add_argument("--period", default="2026Q1", choices=sorted(data.PERIODS))
    parser.add_argument("--compare", choices=sorted(data.PERIODS), help="optional second period")
    parser.add_argument("--monthly", action="store_true", help="also print stability by month")
    args = parser.parse_args()

    ds = data.load(args.data)
    periods = [args.period] + ([args.compare] if args.compare else [])
    rows = [metrics.baseline(data.for_period(ds, p), p) for p in periods]
    print(render(rows))
    if args.monthly:
        print()
        print(render_monthly(metrics.monthly_stability(ds.deployments)))
        print()
        print(render_monthly(metrics.rolling_stability(ds.deployments)).replace("| Month |", "| Rolling 3-month window |"))


if __name__ == "__main__":
    main()

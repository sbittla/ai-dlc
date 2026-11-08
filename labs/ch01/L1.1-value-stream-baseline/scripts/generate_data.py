"""Generate the synthetic Relay delivery dataset used in Lab 1.1.

The dataset covers two quarters of Relay's delivery history:

* 2026-Q1: before coding agents were adopted (the baseline).
* 2026-Q2: after the team adopted coding agents for most changes.

Everything is synthetic and deterministic (fixed seed), so every learner and
every instructor sees the same numbers. Re-run with:

    python scripts/generate_data.py --out data

The generator deliberately encodes the pattern described in Chapter 1's
opening incident: Q2 has roughly twice as many changes, shorter coding time,
longer review queues, larger changes, more failed deployments and more
unplanned (hotfix) deployments.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20260101

# Each quarter is 12 working weeks. Deploy trains leave on Tuesdays and
# Thursdays at 15:00 local time.
QUARTERS = {
    "2026Q1": {
        "start": datetime(2026, 1, 5, 9, 0),
        "weeks": 12,
        "changes_per_week": 8,
        "coding_median_h": 20.0,
        "review_wait_median_h": 6.0,
        "review_median_h": 4.0,
        "lines_median": 120,
        "ai_share": 0.10,
        "failed_deploys": 3,
        "hotfixes": 2,
        "recovery_median_h": 3.0,
        "reverted": 3,
        "costs": {"engineering_usd": 120_000, "ai_tooling_usd": 400, "ci_cloud_usd": 3_000},
    },
    "2026Q2": {
        "start": datetime(2026, 4, 6, 9, 0),
        "weeks": 12,
        "changes_per_week": 16,
        "coding_median_h": 8.0,
        "review_wait_median_h": 18.0,
        "review_median_h": 5.0,
        "lines_median": 260,
        "ai_share": 0.85,
        "failed_deploys": 5,
        "hotfixes": 6,
        "recovery_median_h": 5.0,
        "reverted": 12,
        "costs": {"engineering_usd": 120_000, "ai_tooling_usd": 4_800, "ci_cloud_usd": 5_500},
    },
}

MERGE_WAIT_MEDIAN_H = 2.0
TS = "%Y-%m-%dT%H:%M"


def lognormal_hours(rng: random.Random, median: float, sigma: float = 0.6) -> float:
    """Return a positive duration whose median is `median` hours."""
    return math.exp(math.log(median) + rng.gauss(0.0, sigma))


def deploy_slots(start: datetime, weeks: int) -> list[datetime]:
    """Tuesday and Thursday 15:00 deploy trains for the quarter (plus one spare week)."""
    slots = []
    monday = start - timedelta(days=start.weekday())
    for w in range(weeks + 1):
        week_monday = monday + timedelta(weeks=w)
        for day in (1, 3):  # Tuesday, Thursday
            slots.append(week_monday.replace(hour=15, minute=0) + timedelta(days=day))
    return slots


def next_slot(slots: list[datetime], t: datetime) -> datetime:
    for s in slots:
        if s >= t:
            return s
    raise ValueError(f"no deploy slot after {t}")


def generate(out: Path) -> None:
    rng = random.Random(SEED)
    changes: list[dict] = []
    deployments: list[dict] = []
    costs: list[dict] = []
    change_no = 0
    deploy_no = 0

    for quarter, q in QUARTERS.items():
        slots = deploy_slots(q["start"], q["weeks"])
        quarter_end = q["start"] + timedelta(weeks=q["weeks"])
        n_changes = q["changes_per_week"] * q["weeks"]
        planned: dict[datetime, list[dict]] = {}

        for _ in range(n_changes):
            change_no += 1
            # Work starts uniformly across the first 11 weeks so it can ship in-quarter.
            first_commit = q["start"] + timedelta(hours=rng.uniform(0, (q["weeks"] - 1) * 7 * 24))
            pr_opened = first_commit + timedelta(hours=lognormal_hours(rng, q["coding_median_h"]))
            first_review = pr_opened + timedelta(hours=lognormal_hours(rng, q["review_wait_median_h"]))
            approved = first_review + timedelta(hours=lognormal_hours(rng, q["review_median_h"]))
            merged = approved + timedelta(hours=lognormal_hours(rng, MERGE_WAIT_MEDIAN_H, 0.4))
            slot = next_slot(slots, merged)
            if slot >= quarter_end:
                slot = slots[-1] if slots[-1] < quarter_end else max(s for s in slots if s < quarter_end)
                if slot < merged:  # cannot ship before merge; drop the change from this quarter
                    change_no -= 1
                    continue
            row = {
                "change_id": f"C{change_no:04d}",
                "kind": "feature",
                "first_commit_at": first_commit,
                "pr_opened_at": pr_opened,
                "first_review_at": first_review,
                "approved_at": approved,
                "merged_at": merged,
                "deployed_at": slot,
                "lines_changed": max(5, int(lognormal_hours(rng, q["lines_median"], 0.7))),
                "ai_assisted": rng.random() < q["ai_share"],
                "reverted": False,
            }
            planned.setdefault(slot, []).append(row)

        # Planned deployments: one per deploy train that carried at least one change.
        planned_ids: list[str] = []
        for slot in sorted(planned):
            deploy_no += 1
            dep_id = f"D{deploy_no:04d}"
            planned_ids.append(dep_id)
            for row in planned[slot]:
                row["deploy_id"] = dep_id
                changes.append(row)
            deployments.append(
                {"deploy_id": dep_id, "deployed_at": slot, "kind": "planned", "failed": False, "restored_at": None}
            )

        # Mark exactly the configured number of planned deployments as failed.
        q_deps = [d for d in deployments if d["deploy_id"] in planned_ids]
        failed = rng.sample(q_deps, q["failed_deploys"])
        for d in failed:
            d["failed"] = True
            d["restored_at"] = d["deployed_at"] + timedelta(hours=lognormal_hours(rng, q["recovery_median_h"], 0.5))

        # Hotfix deployments: unplanned, each carrying one small fix change.
        # The first ones follow failed deployments; extra ones are fixes for
        # production defects found later.
        hotfix_anchor = sorted(failed, key=lambda d: d["deployed_at"])
        while len(hotfix_anchor) < q["hotfixes"]:
            hotfix_anchor.append(rng.choice(q_deps))
        for anchor in hotfix_anchor[: q["hotfixes"]]:
            deploy_no += 1
            change_no += 1
            dep_id = f"D{deploy_no:04d}"
            start = anchor["deployed_at"] + timedelta(hours=rng.uniform(1, 30))
            at = start + timedelta(hours=lognormal_hours(rng, 2.0, 0.3))
            deployments.append({"deploy_id": dep_id, "deployed_at": at, "kind": "hotfix", "failed": False, "restored_at": None})
            changes.append(
                {
                    "change_id": f"C{change_no:04d}",
                    "kind": "hotfix",
                    "first_commit_at": start,
                    "pr_opened_at": start + timedelta(minutes=30),
                    "first_review_at": start + timedelta(minutes=45),
                    "approved_at": start + timedelta(minutes=70),
                    "merged_at": start + timedelta(minutes=80),
                    "deployed_at": at,
                    "deploy_id": dep_id,
                    "lines_changed": rng.randint(3, 40),
                    "ai_assisted": rng.random() < q["ai_share"],
                    "reverted": False,
                }
            )

        # Mark exactly the configured number of feature changes as later reverted.
        q_features = [c for c in changes if c["kind"] == "feature" and c["deploy_id"] in planned_ids]
        for c in rng.sample(q_features, q["reverted"]):
            c["reverted"] = True

        # Monthly costs for the three months of the quarter.
        first_month = q["start"].month
        for m in range(first_month, first_month + 3):
            costs.append({"month": f"2026-{m:02d}", **q["costs"]})

    out.mkdir(parents=True, exist_ok=True)
    changes.sort(key=lambda c: c["change_id"])
    deployments.sort(key=lambda d: d["deploy_id"])

    with (out / "changes.csv").open("w", newline="", encoding="utf-8") as f:
        cols = [
            "change_id", "kind", "first_commit_at", "pr_opened_at", "first_review_at", "approved_at",
            "merged_at", "deployed_at", "deploy_id", "lines_changed", "ai_assisted", "reverted",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in changes:
            w.writerow({k: (v.strftime(TS) if isinstance(v, datetime) else str(v).lower() if isinstance(v, bool) else v)
                        for k, v in c.items()})

    with (out / "deployments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["deploy_id", "deployed_at", "kind", "failed", "restored_at"])
        w.writeheader()
        for d in deployments:
            w.writerow({
                "deploy_id": d["deploy_id"],
                "deployed_at": d["deployed_at"].strftime(TS),
                "kind": d["kind"],
                "failed": str(d["failed"]).lower(),
                "restored_at": d["restored_at"].strftime(TS) if d["restored_at"] else "",
            })

    with (out / "costs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "engineering_usd", "ai_tooling_usd", "ci_cloud_usd"])
        w.writeheader()
        w.writerows(costs)

    print(f"wrote {len(changes)} changes, {len(deployments)} deployments, {len(costs)} cost rows to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    generate(parser.parse_args().out)

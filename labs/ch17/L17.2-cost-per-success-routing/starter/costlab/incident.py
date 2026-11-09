"""The opening incident replayed day by day: what the month cost, and when a spend monitor would have spoken.

A composite. Daily ticket counts repeat Lab 17.1's generated week by weekday (Wednesday without its outage).
Each day's cost and successes are that day's tickets times the configuration's cost per run and quality, from
compare.py: expected values, not a draw. The monitor is relay.routing.SpendMonitor with Chapter 7's 25% tolerance,
run two ways. On cost per suggestion delivered it needs no labels, so production could run it daily. On cost per
correct triage it needs a daily count of correct suggestions, which production does not have: correctness arrives
from people's confirmations and the weekly labelled sample, tens a day and hours late (Chapter 16).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta

from relay.routing import SpendMonitor

from . import DATA_DIR, load_json
from .compare import summarize, run_config

INCIDENT = load_json(DATA_DIR / "incident.json")
OUTAGE_TICKETS = 300


def tickets_by_weekday() -> list[int]:
    """Monday-first ticket counts of the generated week, Wednesday's outage removed."""
    days = [0] * 7
    with open(DATA_DIR / "source" / "tickets-per-minute.csv", newline="", encoding="utf-8") as f:
        for row in list(csv.reader(f))[1:]:
            days[int(row[0]) // 1440] += int(row[1])
    days[2] -= OUTAGE_TICKETS
    return days


@dataclass(frozen=True)
class Replay:
    first_day: str
    last_day: str
    days: int
    tickets: int
    cost_new: float           # what the period cost on the new model
    cost_old: float           # what it would have cost on the old one
    first_alert: str | None   # monitor on cost per correct triage: needs daily correctness labels
    alert_value: float | None
    to_a_person: float        # expected tickets handed to a person under the new model
    call_ratio: float         # cost per call, new / old
    suggestion_alert: str | None   # monitor on cost per suggestion delivered: needs no labels
    suggestion_value: float | None
    suggestion_baseline: float


def replay() -> Replay:
    start = date.fromisoformat(INCIDENT["switched"]) + timedelta(days=1)  # first full day after the 15:00 train
    end = date.fromisoformat(INCIDENT["noticed"])
    old, new = summarize("large", run_config("large")), summarize("reasoner", run_config("reasoner"))
    per_day = tickets_by_weekday()
    series, by_suggestion, tickets, d = [], [], 0, start - timedelta(days=3)
    while d <= end:
        n = per_day[d.weekday()]
        s = new if d >= start else old
        series.append((d.isoformat(), n * s.usd_per_run, round(n * s.quality)))
        by_suggestion.append((d.isoformat(), n * s.usd_per_run, round(n * (s.correct + s.wrong) / s.runs)))
        if d >= start:
            tickets += n
        d += timedelta(days=1)

    def first_after(alerts):
        return next((a for a in alerts if a.day >= start.isoformat() and a.kind == "cost_per_success"), None)

    labelled = first_after(SpendMonitor(baseline_per_success=old.usd_per_correct).check(series))
    base_sugg = old.usd_per_run * old.runs / (old.correct + old.wrong)
    unlabelled = first_after(SpendMonitor(baseline_per_success=base_sugg).check(by_suggestion))
    return Replay(start.isoformat(), end.isoformat(), (end - start).days + 1, tickets, tickets * new.usd_per_run,
                  tickets * old.usd_per_run, labelled.day if labelled else None, labelled.value if labelled else None,
                  tickets * new.needs_human / new.runs, new.usd_per_call / old.usd_per_call,
                  unlabelled.day if unlabelled else None, unlabelled.value if unlabelled else None, base_sugg)

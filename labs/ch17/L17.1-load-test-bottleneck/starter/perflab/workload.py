"""A workload model from a week of traffic: rates, peaks, mix and concurrency (reference solution).

The model is what a load test reproduces. It answers: how many requests arrive per second on average and at
the busiest minute, which journeys they are, how many callers send them, and so how fast the test must send
and in what mix. Peaks are judged by the minute, because a one-minute peak hidden inside an hourly average is
exactly what overloads a service.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import DATA_DIR, load_json

HEADROOM = 2.0  # the test runs at twice the busiest minute (ADR-040)
START = datetime(2027, 2, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class WorkloadModel:
    minutes: int
    totals: dict[str, int]          # requests per journey over the week
    mean_rate: float                # requests per second over the week
    peak_minute: int                # minute index of the busiest minute
    peak_minute_rate: float         # requests per second in that minute
    peak_hour: int                  # hour index (0 = Monday 00:00 UTC) of the busiest hour
    peak_hour_rate: float           # requests per second in that hour
    peak_hour_mix: dict[str, float]  # each journey's share of the peak hour's requests, rounded to 3 places
    tickets_per_weekday: float      # mean POST /v1/triage-jobs per Monday-Friday day
    tokens: int
    test_rate: int                  # HEADROOM x peak_minute_rate, rounded up to a multiple of 10

    @property
    def peak_to_mean(self) -> float:
        return self.peak_minute_rate / self.mean_rate


def load_traffic(path: Path | None = None) -> tuple[list[str], list[list[int]]]:
    path = path or DATA_DIR / "traffic" / "week-2027-02-01.csv"
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    journeys = rows[0][1:]
    return journeys, [[int(v) for v in r[1:]] for r in rows[1:]]


def when(minute: int) -> str:
    """'Mon 2027-02-01 09:00' for a minute index."""
    return (START + timedelta(minutes=minute)).strftime("%a %Y-%m-%d %H:%M")


def build_model(journeys: list[str], rows: list[list[int]], tokens: int) -> WorkloadModel:
    """TODO 1. Build the workload model from per-minute counts (one row per minute, one column per journey).

    - totals: the sum of each journey's column.
    - mean_rate: all requests / (minutes x 60).
    - peak_minute: the index of the minute with the most requests in all (the first, on a tie);
      peak_minute_rate: that minute's requests / 60.
    - peak_hour: the hour h (rows 60h to 60h+59) with the most requests (the first, on a tie);
      peak_hour_rate: its requests / 3600; peak_hour_mix: each journey's share of the peak hour's requests,
      rounded to 3 places.
    - tickets_per_weekday: the post_triage_job total over the first 5 days (7,200 minutes) / 5.
    - test_rate: HEADROOM x peak_minute_rate rounded UP to a multiple of 10 (math.ceil(x / 10) * 10).
    """
    raise NotImplementedError("TODO 1")


def concurrency(rate_per_s: float, mean_time_s: float) -> float:
    """Little's law: the mean number in the system is the arrival rate times the mean time each spends in it.

    It holds for any stable system over a long enough period, whatever the distributions, but only for means:
    it says nothing about percentiles, and nothing about a period in which the queue is still growing.
    """
    return rate_per_s * mean_time_s


def model() -> WorkloadModel:
    journeys, rows = load_traffic()
    meta = load_json(DATA_DIR / "traffic" / "meta.json")
    return build_model(journeys, rows, meta["tokens_at_peak"])


def as_workload_json(m: WorkloadModel) -> dict:
    """The model as Relay's perf/workload.json holds it (what tools/loadtest.py reads)."""
    return {"name": "relay-api-weekday-peak", "version": "2027.02.1",
            "source": "Lab 17.1 workload model of the week of 1 February 2027 (synthetic traffic)",
            "tokens": m.tokens, "test_rate_per_s": m.test_rate, "peak_minute_rate_per_s": round(m.peak_minute_rate, 2),
            "headroom": HEADROOM, "mix": m.peak_hour_mix}

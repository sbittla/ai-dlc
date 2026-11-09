"""Read load-test runs, find where the time goes, and measure the worker's claim as its table grows.

The runs in data/measured/ were recorded with relay-repo/tools/loadtest.py on the author's machine (each file
records its environment). Their latencies are that machine's. What transfers is the comparison: the same
schedule, the same machine, configurations interleaved run by run, and five runs to show the spread.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from . import DATA_DIR, load_json
from .stats import mean_interval, summarize

MEASURED = DATA_DIR / "measured"


@dataclass(frozen=True)
class ConfigResult:
    config: str
    runs: int
    requests: int                 # steady-state requests per run
    p50: tuple[float, float, float]   # (mean, low, high) over runs, ms
    p95: tuple[float, float, float]
    p99: tuple[float, float, float]
    worst_max_ms: float
    errors: int                   # over all runs
    app_ms_per_request: float     # time inside the application, per request, over all runs and servers
    limiter_ms_per_request: float
    limiter_share: float          # limiter time / application time
    limiter_tx_per_request: float


def config_result(runs: list[dict], config: str) -> ConfigResult:
    """TODO 4a. Summarize one configuration's runs.

    For each run, summarize `latency_from_due_us` (stats.summarize); report the mean and 95% interval of the
    per-run p50, p95 and p99 (stats.mean_interval), and the largest max. Errors count `errors` entries over all
    runs. Server counters are pooled over all runs and servers: app_ms_per_request = sum(app_s) x 1000 /
    sum(requests), and likewise for limiter_s; limiter_share = sum(limiter_s) / sum(app_s);
    limiter_tx_per_request = sum(limiter_transactions) / sum(requests).
    """
    raise NotImplementedError("TODO 4")


def paired_ratio(runs: list[dict], stat: str, before: str = "exact", after: str = "lease") -> tuple[float, float, float]:
    """TODO 4b. after/before ratio of a per-run statistic ('p50_ms', 'p95_ms' or 'p99_ms'), paired by run number,
    with its 95% t-interval over the pairs (stats.mean_interval of the per-pair ratios)."""
    raise NotImplementedError("TODO 4")


def load(name: str) -> dict:
    return load_json(MEASURED / name)


def stress_table(rates: list[int]) -> list[tuple[int, str, float, float, int]]:
    """(rate, config, mean p99 ms, max p99 ms over runs, errors) for the test rate's steady file and each stress file."""
    out = []
    for rate in rates:
        data = load(f"steady-{rate}.json") if (MEASURED / f"steady-{rate}.json").exists() else load(f"stress-{rate}.json")
        for config in ("exact", "lease"):
            mine = [r for r in data["runs"] if r["config"] == config]
            p99s = [summarize(r["latency_from_due_us"]).p99_ms for r in mine]
            out.append((rate, config, sum(p99s) / len(p99s), max(p99s), sum(len(r["errors"]) for r in mine)))
    return out


# ------------------------------------------------------------------ the worker's claim as the table grows (soak)

INDEX = ("CREATE INDEX IF NOT EXISTS triage_jobs_open ON triage_jobs (status, available_at)")  # merge note, ADR-040


@dataclass(frozen=True)
class ClaimCost:
    done_rows: int
    indexed: bool
    vm_steps: int        # SQLite virtual-machine instructions for one claim, in units of 10
    plan: tuple[str, ...]
    ms: float            # median of 5 claims, this machine


def claim_cost(done_rows: int, indexed: bool) -> ClaimCost:
    """TODO 4c. What one `TriageQueue.claim` costs with `done_rows` finished jobs in the table.

    Build a queue on ":memory:" with Relay's own schema, insert `done_rows` jobs with status 'done' in one
    transaction (ids 1..done_rows), create INDEX if `indexed`, then for each of 5 rounds enqueue one new job
    and claim it, timing the claim. Count virtual-machine steps on the first claim with
    conn.set_progress_handler(callback, 10), and read the query plan of the claim's SELECT with
    EXPLAIN QUERY PLAN (the last column of each row). Return the median time in ms.
    """
    raise NotImplementedError("TODO 4")


def sqlite_version() -> str:
    return sqlite3.sqlite_version


def measured_environment(name: str) -> dict:
    return load(name)["environment"]


def path(name: str) -> Path:
    return MEASURED / name


def lease_transactions_at_workload(block: int = 10) -> tuple[int, int]:
    """(rate-limited requests, limiter write transactions) for the workload's 25-second schedule through two
    limiters taking requests in turn, all in one window (provided; relay-repo/tests/test_loadtest.py checks it)."""
    import tempfile

    import loadtest
    from relay.service.directory import token_hash
    from relay.service.sharedlimit import SharedRateLimiter

    workload = load_json(MEASURED.parent.parent / "relay-repo" / "perf" / "workload.json")
    arrivals = loadtest.schedule(workload, workload["test_rate_per_s"], 25, seed=17)
    with tempfile.TemporaryDirectory() as tmp:
        lims = [SharedRateLimiter(str(Path(tmp) / "r.db"), block=block) for _ in range(2)]
        calls = 0
        for a in arrivals:
            if a.journey != "healthz":
                calls += 1
                lims[a.index % 2].check(token_hash(f"lt-token-{a.token}"), 1_800_000_000.0 + a.due_s)
        tx = sum(lim.transactions for lim in lims)
        for lim in lims:
            lim.close()
    return calls, tx


def generator_lag(runs: list[dict], config: str) -> tuple[float, float]:
    """Mean over runs of the nearest-rank p50 and p99 of (sent - due), in ms (provided).

    This checks the load generator, not the server: if requests leave late, the tool fell behind its own
    schedule. Latency is still timed from the due time, so lateness is charged to the measurement, never hidden.
    """
    from .stats import percentile

    p50s, p99s = [], []
    for r in runs:
        if r["config"] != config:
            continue
        lags = sorted(a - b for a, b in zip(r["latency_from_due_us"], r["latency_from_sent_us"]))
        p50s.append(percentile(lags, 50) / 1000)
        p99s.append(percentile(lags, 99) / 1000)
    return sum(p50s) / len(p50s), sum(p99s) / len(p99s)

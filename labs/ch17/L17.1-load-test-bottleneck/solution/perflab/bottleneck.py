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
    mine = [r for r in runs if r["config"] == config]
    sums = [summarize(r["latency_from_due_us"]) for r in mine]
    servers = [s for r in mine for s in r["servers"]]
    req = sum(s["requests"] for s in servers)
    app = sum(s["app_s"] for s in servers)
    lim = sum(s["limiter_s"] for s in servers)
    return ConfigResult(config, len(mine), sums[0].n, mean_interval([s.p50_ms for s in sums]),
                        mean_interval([s.p95_ms for s in sums]), mean_interval([s.p99_ms for s in sums]),
                        max(s.max_ms for s in sums), sum(len(r["errors"]) for r in mine),
                        app * 1000 / req, lim * 1000 / req, lim / app,
                        sum(s["limiter_transactions"] for s in servers) / req)


def paired_ratio(runs: list[dict], stat: str, before: str = "exact", after: str = "lease") -> tuple[float, float, float]:
    """TODO 4b. after/before ratio of a per-run statistic ('p50_ms', 'p95_ms' or 'p99_ms'), paired by run number,
    with its 95% t-interval over the pairs (stats.mean_interval of the per-pair ratios)."""
    by = {(r["config"], r["run"]): getattr(summarize(r["latency_from_due_us"]), stat) for r in runs}
    pairs = sorted({n for c, n in by if c == before} & {n for c, n in by if c == after})
    return mean_interval([by[(after, n)] / by[(before, n)] for n in pairs])


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
    from relay.worker import TriageQueue

    q = TriageQueue(":memory:")
    c = q.conn
    c.execute("BEGIN")
    c.executemany("INSERT INTO triage_jobs (workspace, idempotency_key, body_sha256, ticket_text, status, attempts, "
                  "available_at, result, created_at, updated_at) VALUES ('ws', ?, 'x', 'old ticket', 'done', 1, 0, "
                  "'{}', 0, 0)", [(f"old-{i}",) for i in range(done_rows)])
    c.execute("COMMIT")
    if indexed:
        c.execute(INDEX)
    times, steps = [], [0]
    for k in range(5):
        q.enqueue("ws", f"new-job-{k:03d}", f"new ticket {k}", 100.0 + k)
        if k == 0:
            c.set_progress_handler(lambda: steps.__setitem__(0, steps[0] + 1), 10)
        t0 = time.perf_counter()
        job = q.claim("worker-1", 200.0 + k, 60.0)
        times.append((time.perf_counter() - t0) * 1000)
        c.set_progress_handler(None, 0)
        if job is None:
            raise AssertionError("the new job was not claimed")
        q.complete(job.id, "worker-1", {"suggestion": {}}, 201.0 + k)
    plan = tuple(row[-1] for row in c.execute(
        "EXPLAIN QUERY PLAN SELECT id, status, attempts FROM triage_jobs WHERE (status = 'queued' AND available_at <= ?) "
        "OR (status = 'running' AND lease_until < ?) ORDER BY id LIMIT 1", (0, 0)))
    return ClaimCost(done_rows, indexed, steps[0], plan, sorted(times)[2])


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

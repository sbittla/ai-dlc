"""Lab 17.1's reports (provided). Run from starter/ or solution/:

    python -m perflab.report workload    # the workload model of the generated week (TODO 1)
    python -m perflab.report omission    # one stall measured three ways (TODOs 2, 3)
    python -m perflab.report runs        # the recorded load test: before and after the limiter fix (TODOs 2, 4)
    python -m perflab.report stress      # p99 as the rate rises, both limiters (TODO 4)
    python -m perflab.report soak        # the worker's claim as its table grows (TODO 4)
    python -m perflab.report worker      # triage workers needed at the peak and in the outage (TODO 5)
    python -m perflab.report budgets     # every budget in relay-repo/perf/budgets.json, checked (TODOs 1-5)
    python -m perflab.report live --out ../evidence/my-runs.json   # run the load test on THIS machine
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys

from . import RELAY, load_json
from .bottleneck import (claim_cost, config_result, generator_lag, lease_transactions_at_workload, load,
                         measured_environment, paired_ratio, sqlite_version, stress_table)
from .capacity import arrivals, table as capacity_table
from .omission import Scenario, views
from .workload import as_workload_json, concurrency, model, when

BUDGETS = load_json(RELAY / "perf" / "budgets.json")
STEADY = "steady-140.json"
SOAK_ROWS = (10_000, 33_000, 400_000)


def ival(t: tuple[float, float, float], digits: int = 2) -> str:
    return f"{t[0]:.{digits}f} ({t[1]:.{digits}f} to {t[2]:.{digits}f})"


def render_workload() -> str:
    m = model()
    lines = ["# Workload model: the week of 1 February 2027 (synthetic, generated traffic)", "",
             "| Journey | Requests in the week | Share of the peak hour |", "| --- | ---: | ---: |"]
    for j, n in m.totals.items():
        lines.append(f"| {j} | {n:,} | {m.peak_hour_mix[j]:.1%} |")
    lines += ["", f"Mean rate: {m.mean_rate:.1f} requests/s over {m.minutes:,} minutes.",
              f"Busiest minute: {when(m.peak_minute)} UTC, {m.peak_minute_rate:.1f} requests/s "
              f"({m.peak_to_mean:.1f} times the mean).",
              f"Busiest hour: {when(m.peak_hour * 60)} UTC, {m.peak_hour_rate:.1f} requests/s.",
              f"Support tickets queued for triage: {m.totals['post_triage_job']:,} in the week, "
              f"{m.tickets_per_weekday:,.1f} per weekday.",
              f"Callers active in the peak hour: {m.tokens} tokens.",
              f"Test rate: {m.test_rate} requests/s (twice the busiest minute, rounded up to 10).",
              f"Little's law at the busiest minute: {concurrency(m.peak_minute_rate, 0.002):.2f} requests in the "
              f"service at a mean of 2 ms each; {concurrency(m.peak_minute_rate, 0.020):.2f} at 20 ms.",
              f"At 10% traffic growth a month, twice the busiest minute lasts {math.log(2) / math.log(1.1):.1f} months.",
              f"A page of 8 calls has at least one call past its p99 in {1 - 0.99 ** 8:.1%} of loads (independent calls).",
              "relay-repo/perf/workload.json matches this model: "
              f"{'yes' if load_json(RELAY / 'perf' / 'workload.json') == as_workload_json(m) else 'NO'}."]
    return "\n".join(lines)


def render_omission() -> str:
    sc = Scenario()
    lines = ["# One stall, three measurements (simulated)", "",
             f"Server: {sc.service_ms:g} ms per request, one at a time, stops for {sc.stall_s:g} s at "
             f"{sc.stall_at_s:g} s. Intended: one request every {sc.interval_ms:g} ms for {sc.duration_s:g} s.", "",
             "| Measurement | Samples | p50 (ms) | p99 (ms) | p99.9 (ms) | Max (ms) |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for v in views(sc):
        lines.append(f"| {v.name} | {v.samples:,} | {v.p50_ms:.1f} | {v.p99_ms:.1f} | {v.p999_ms:.1f} | {v.max_ms:.1f} |")
    return "\n".join(lines)


def render_runs() -> str:
    data = load(STEADY)
    env = data["environment"]
    lines = [f"# Load test at {data['rate_per_s']:g} requests/s: 4.21.0's exact limiter against 4.28.0's leases", "",
             f"Recorded on {env['platform']}, {env['cpus']} logical CPUs, "
             f"Python {env['python']}, SQLite {env['sqlite']}. These are that machine's numbers.",
             f"Schedule: {data['arrivals']:,} arrivals (seed {data['seed']}), {data['warmup_s']:g} s warm-up "
             f"discarded, {data['duration_s']:g} s steady state; {data['servers']} service processes, "
             f"{data['threads']} client threads, one worker; {len(data['runs']) // 2} runs per configuration, interleaved.",
             "", "| Limiter | Requests per run | p50 (ms) | p95 (ms) | p99 (ms) | Worst max (ms) | Errors |",
             "| --- | ---: | --- | --- | --- | ---: | ---: |"]
    results = [config_result(data["runs"], c) for c in ("exact", "lease")]
    for r in results:
        lines.append(f"| {r.config} | {r.requests:,} | {ival(r.p50)} | {ival(r.p95)} | {ival(r.p99)} | "
                     f"{r.worst_max_ms:.1f} | {r.errors} |")
    lines += ["", "Means over runs, with 95% t-intervals in brackets.", "",
              "| Limiter | App time per request (ms) | Limiter time per request (ms) | Limiter share | "
              "Limiter transactions per request |", "| --- | ---: | ---: | ---: | ---: |"]
    for r in results:
        lines.append(f"| {r.config} | {r.app_ms_per_request:.3f} | {r.limiter_ms_per_request:.3f} | "
                     f"{r.limiter_share:.1%} | {r.limiter_tx_per_request:.3f} |")
    lines.append("")
    for stat, label in (("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99")):
        lines.append(f"Paired by run, lease / exact {label}: {ival(paired_ratio(data['runs'], stat), 3)}.")
    for c in ("exact", "lease"):
        lag50, lag99 = generator_lag(data["runs"], c)
        lines.append(f"Generator lag (sent - due), {c}: p50 {lag50:.2f} ms, p99 {lag99:.2f} ms (mean over runs).")
    calls, tx = lease_transactions_at_workload()
    exact_tx = lease_transactions_at_workload(block=1)[1]
    lines.append(f"No timing: the workload's 25-second schedule makes {calls:,} rate-limited requests; leases cost {tx} "
                 f"write transactions ({tx / calls:.3f} per request), the exact limiter {exact_tx:,}.")
    return "\n".join(lines)


def render_stress() -> str:
    rates = [140, 280, 420, 560]
    lines = ["# p99 as the rate rises (recorded on the same machine as `runs`)", "",
             "| Rate (requests/s) | Limiter | Mean p99 (ms) | Worst run's p99 (ms) | Errors | Within the 50 ms budget |",
             "| ---: | --- | ---: | ---: | ---: | --- |"]
    for rate, config, mean, worst, errors in stress_table(rates):
        ok = worst <= BUDGETS["service"]["p99_ms"] and errors == 0
        lines.append(f"| {rate} | {config} | {mean:.1f} | {worst:.1f} | {errors} | {'yes' if ok else 'no'} |")
    env = measured_environment("stress-560.json")
    lines += ["", f"Stress runs: 3 per configuration and rate, 20 s steady state."]
    return "\n".join(lines)


def render_soak() -> str:
    lines = ["# The worker's claim as its table fills with finished jobs", "",
             f"SQLite {sqlite_version()} on this machine. VM steps are SQLite's own instruction count for one "
             "claim (in units of 10); they depend on the SQLite version, not on the machine's speed. Milliseconds are this machine's.", "",
             "| Finished jobs | Index | VM steps (x10) | Claim (ms, median of 5) | Plan |", "| ---: | --- | ---: | ---: | --- |"]
    pairs = []
    for n in SOAK_ROWS:
        a, b = claim_cost(n, False), claim_cost(n, True)
        pairs.append((a, b))
        for c in (a, b):
            lines.append(f"| {n:,} | {'yes' if c.indexed else 'no'} | {c.vm_steps:,} | {c.ms:.2f} | "
                         f"{'; '.join(c.plan)} |")
    lines += ["", "Without the index the claim reads every finished job, inside BEGIN IMMEDIATE, so it holds the "
              "database's write lock while it scans. At 1,380 tickets a weekday the table gains about 33,000 jobs a month.",
              "Index (merge note, ADR-040): CREATE INDEX triage_jobs_open ON triage_jobs (status, available_at)."]
    return "\n".join(lines)


def render_worker() -> str:
    budget = BUDGETS["worker"]["time_to_suggestion_p95_s"]
    lines = ["# Triage workers needed (Relay's worker and queue in simulated time; simulated model, median 2.4 s)", "",
             "| Scenario | Workers | Tickets | Done | To a person | p50 (s) | p95 (s) | Max (s) | Most queued | "
             "Longest gap between passes (s) | p95 within 30 s |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for r in capacity_table():
        lines.append(f"| {r.scenario} | {r.workers} | {r.tickets} | {r.done} | {r.needs_human} | {r.p50_s:.1f} | "
                     f"{r.p95_s:.1f} | {r.max_s:.1f} | {r.max_queued} | {r.longest_gap_s:.1f} | "
                     f"{'yes' if r.p95_s <= budget else 'no'} |")
    first = sum(1 for t in arrivals("outage") if t < arrivals("outage")[0] - arrivals("outage")[0] % 60 + 600)
    peak = len(arrivals("peak-hour"))
    lines += ["", "peak-hour: Monday 1 February 09:00-10:00 UTC. outage: Wednesday 3 February 14:00-15:00 UTC, "
              "300 extra tickets in the first ten minutes.",
              f"Little's law at 2.4 s a job (the simulator's median): busiest hour {peak / 60:.1f} tickets a minute, {peak / 3600 * 2.4:.2f} busy "
              f"workers; outage's first ten minutes {first / 10:.1f} a minute, {first / 600 * 2.4:.2f} busy workers."]
    return "\n".join(lines)


def render_budgets() -> str:
    b = BUDGETS
    data = load(STEADY)
    lines = [f"# Budgets ({b['version']}, {b['decided_in']})", ""]
    for c in ("exact", "lease"):
        r = config_result(data["runs"], c)
        ok = (r.p99[2] <= b["service"]["p99_ms"] and r.errors == 0
              and r.limiter_tx_per_request <= b["service"]["max_limiter_transactions_per_request"])
        lines.append(f"- Service, {c} limiter, at {data['rate_per_s']:g}/s: p99 {ival(r.p99, 1)} ms (budget "
                     f"{b['service']['p99_ms']} ms), errors {r.errors}, limiter transactions per request "
                     f"{r.limiter_tx_per_request:.3f} (budget {b['service']['max_limiter_transactions_per_request']}): "
                     f"{'PASS' if ok else 'FAIL'}.")
    for r in capacity_table(worker_counts=(b["worker"]["workers"],)):
        ok = r.p95_s <= b["worker"]["time_to_suggestion_p95_s"]
        lines.append(f"- Worker, {r.scenario}, {r.workers} workers: p95 time to suggestion {r.p95_s:.1f} s "
                     f"(budget {b['worker']['time_to_suggestion_p95_s']} s): {'PASS' if ok else 'FAIL'}.")
    return "\n".join(lines)


def run_live(out: str, runs: int, duration: float) -> int:
    """Run Relay's load test on this machine. Your numbers will differ from data/measured/: that is the point."""
    cmd = [sys.executable, str(RELAY / "tools" / "loadtest.py"), "run", "--runs", str(runs),
           "--duration", str(duration), "--out", out]
    return subprocess.run(cmd, cwd=RELAY).returncode


RENDER = {"workload": render_workload, "omission": render_omission, "runs": render_runs, "stress": render_stress,
          "soak": render_soak, "worker": render_worker, "budgets": render_budgets}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m perflab.report")
    ap.add_argument("what", choices=sorted(RENDER) + ["live"])
    ap.add_argument("--out", default="../evidence/my-runs.json")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--duration", type=float, default=30.0)
    args = ap.parse_args(argv)
    if args.what == "live":
        return run_live(args.out, args.runs, args.duration)
    sys.stdout.write(RENDER[args.what]() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

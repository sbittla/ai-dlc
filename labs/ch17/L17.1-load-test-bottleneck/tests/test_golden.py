"""Golden tests: every number Chapter 17 quotes from Lab 17.1. A change that moves one must fail here.

The load-test latencies come from the committed runs in data/measured/ (recorded on the author's machine), so
they are fixed here even though a new run on any machine would differ. The soak test's VM-step counts depend on
the SQLite version, so they are checked within a band; their query plans are checked exactly.
"""

import sqlite3

from perflab.bottleneck import claim_cost
from perflab.report import (render_budgets, render_omission, render_runs, render_stress, render_worker,
                            render_workload)


def test_workload():
    t = render_workload()
    for s in ("| get_task | 8,200,926 | 81.7% |", "| get_escalation | 1,088,829 | 10.8% |",
              "| get_triage_job | 545,398 | 5.4% |", "| post_triage_job | 7,586 | 0.1% |", "| healthz | 604,800 | 2.0% |",
              "Mean rate: 17.3 requests/s over 10,080 minutes.",
              "Busiest minute: Mon 2027-02-01 09:00 UTC, 65.2 requests/s (3.8 times the mean).",
              "Busiest hour: Mon 2027-02-01 09:00 UTC, 50.5 requests/s.",
              "7,586 in the week, 1,380.6 per weekday.", "Callers active in the peak hour: 40 tokens.",
              "Test rate: 140 requests/s", "twice the busiest minute lasts 7.3 months.", "at least one call past its p99 in 7.7% of loads", "0.13 requests in the service at a mean of 2 ms each; 1.30 at 20 ms.",
              "relay-repo/perf/workload.json matches this model: yes."):
        assert s in t, s


def test_omission():
    t = render_omission()
    assert "| open schedule, from due time | 2,000 | 1.0 | 821.0 | 992.0 | 1001.0 |" in t
    assert "| closed loop, from send time | 1,901 | 1.0 | 1.0 | 1.0 | 1001.0 |" in t
    assert "| closed loop, corrected | 2,001 | 1.0 | 801.0 | 981.0 | 1001.0 |" in t


def test_runs():
    t = render_runs()
    for s in ("4,925 arrivals (seed 17), 5 s warm-up discarded, 30 s steady state; 2 service processes, 64 client "
              "threads, one worker; 5 runs per configuration, interleaved.",
              "| exact | 4,197 | 4.59 (4.20 to 4.98) | 20.88 (19.68 to 22.09) | 33.37 (30.18 to 36.56) | 81.5 | 0 |",
              "| lease | 4,197 | 3.52 (3.26 to 3.78) | 5.48 (5.14 to 5.83) | 10.60 (7.62 to 13.57) | 35.4 | 0 |",
              "| exact | 2.939 | 2.625 | 89.3% | 0.981 |", "| lease | 0.569 | 0.265 | 46.5% | 0.106 |",
              "lease / exact p50: 0.768 (0.741 to 0.795).", "lease / exact p95: 0.263 (0.260 to 0.266).",
              "lease / exact p99: 0.318 (0.237 to 0.399).", "24 logical CPUs, Python 3.13.14, SQLite 3.50.4",
              "Generator lag (sent - due), exact: p50 0.51 ms, p99 1.17 ms (mean over runs).",
              "Generator lag (sent - due), lease: p50 0.56 ms, p99 1.37 ms (mean over runs).",
              "makes 3,428 rate-limited requests; leases cost 376 write transactions (0.110 per request), "
              "the exact limiter 3,428."):
        assert s in t, s


def test_stress():
    t = render_stress()
    for s in ("| 140 | exact | 33.4 | 35.9 | 0 | yes |", "| 140 | lease | 10.6 | 13.1 | 0 | yes |",
              "| 280 | exact | 62.0 | 67.1 | 0 | no |", "| 280 | lease | 7.4 | 7.5 | 0 | yes |",
              "| 420 | exact | 137.0 | 181.4 | 0 | no |", "| 420 | lease | 9.3 | 10.3 | 0 | yes |",
              "| 560 | exact | 177.1 | 214.8 | 0 | no |", "| 560 | lease | 12.0 | 13.9 | 0 | yes |"):
        assert s in t, s


def test_worker():
    t = render_worker()
    for s in ("| peak-hour | 1 | 131 | 131 | 0 | 3.2 | 7.2 | 16.4 | 2 | 5.8 | yes |",
              "| peak-hour | 2 | 131 | 131 | 0 | 2.9 | 6.3 | 15.9 | 1 | 5.8 | yes |",
              "| outage | 1 | 409 | 409 | 0 | 100.7 | 229.7 | 260.6 | 93 | 5.8 | no |",
              "| outage | 2 | 409 | 409 | 0 | 3.6 | 13.9 | 21.4 | 8 | 5.8 | yes |",
              "| outage | 3 | 409 | 409 | 0 | 3.0 | 13.1 | 19.2 | 4 | 5.8 | yes |",
              "busiest hour 2.2 tickets a minute, 0.09 busy workers; outage's first ten minutes 31.8 a minute, "
              "1.27 busy workers."):
        assert s in t, s


def test_budgets():
    t = render_budgets()
    assert "exact limiter, at 140/s: p99 33.4 (30.2 to 36.6) ms" in t and "0.981 (budget 0.2): FAIL." in t
    assert "lease limiter, at 140/s: p99 10.6 (7.6 to 13.6) ms" in t and "0.106 (budget 0.2): PASS." in t
    assert "Worker, outage, 2 workers: p95 time to suggestion 13.9 s (budget 30 s): PASS." in t


def test_soak_plans_and_steps():
    plain, indexed = claim_cost(400_000, False), claim_cost(400_000, True)
    assert plain.plan == ("SCAN triage_jobs",)
    assert "SEARCH triage_jobs USING INDEX triage_jobs_open (status=? AND available_at<?)" in indexed.plan
    assert 150_000 <= plain.vm_steps <= 250_000   # about five instructions per row
    assert indexed.vm_steps <= 100
    if sqlite3.sqlite_version == "3.50.4":        # the version the chapter's Table 17.5 was printed with
        steps = [claim_cost(n, False).vm_steps for n in (10_000, 33_000)]
        assert (steps, plain.vm_steps, indexed.vm_steps) == ([5_011, 16_511], 200_011, 16)

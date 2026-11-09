# Lab 17.1 — Load-Test Baseline, Bottleneck, Fix and Re-Measure

| | |
| --- | --- |
| Chapter | 17 — Performance and AI Cost Engineering |
| Type | Core (all tracks) |
| Time | 4 hours |
| Cost ceiling | $0. Runs on your machine: the load test binds to 127.0.0.1, and the triage model is simulated |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

Chapter 11 kept Relay's rate limit in the database and accepted "one small write per request" on the claim
that it was well within a small instance's capacity. Chapter 6 left the service and worker untested under
load. In this lab you check both claims. You build the workload model from a week of traffic, learn how a
load generator can hide a stall, read a real load test of Relay's service before and after the limiter fix,
find the next bottleneck in the worker, and work out how many triage workers the ticket peaks need.

You have **Relay 4.28.0** in `relay-repo/`: canonical 4.25.0 plus `tools/loadtest.py` and `perf/` (the
workload model and budgets, ADR-040), the shared limiter's leases (ADR-041), and the `relay.routing` package
that Lab 17.2 uses (ADR-042, ADR-043).

**About the data.** `data/traffic/` is **generated** by `scripts/generate_data.py`: synthetic per-minute
counts for one week, whose shape was **configured**. `data/measured/` is **not generated**. It holds load-test
runs recorded with `relay-repo/tools/loadtest.py` on the author's laptop (Windows 11, 24 logical CPUs,
Python 3.13, SQLite 3.50.4; each file records its environment). Those milliseconds are that machine's. Yours
will differ, and step 6 asks you to measure your own. The worker's latencies come from Relay's simulated triage
model (median 2.4 s), so worker capacity is a statement about that configuration.

## What you will practise

- Turning traffic counts into a **workload model**: rates, the busiest minute, the mix and a test rate.
- Measuring latency from the **due time** on an **open schedule**, and seeing coordinated omission.
- Reporting **percentiles** with run-to-run intervals, and comparing configurations run by run.
- Finding a **bottleneck** from server-side time, then re-measuring after the fix.
- Sizing workers with **Little's law** and a simulation of Relay's real worker.

## Folder layout

```
L17.1-load-test-bottleneck/
├── relay-repo/                 ← Relay 4.28.0 (Chapter 17 branch): canonical 4.25.0 + load test and cost controls; 655 tests
│   ├── tools/loadtest.py       ← open-schedule load test of the production WSGI app on 127.0.0.1
│   ├── perf/                   ← workload.json (the model you derive), budgets.json (ADR-040)
│   ├── src/relay/service/sharedlimit.py  ← leases of ten counts (ADR-041)
│   ├── src/relay/routing/      ← prices, routes, spend quotas (Lab 17.2)
│   └── docs/adr/               ← ADR-040 to ADR-043
├── data/
│   ├── traffic/                ← GENERATED: week-2027-02-01.csv (per-minute counts), meta.json
│   └── measured/               ← RECORDED on the author's machine: steady-140.json, stress-280/420/560.json
├── scripts/generate_data.py
├── starter/perflab/
│   ├── workload.py             ← TODO 1: build_model
│   ├── stats.py                ← TODO 2: percentile, summarize, mean_interval
│   ├── omission.py             ← TODO 3: open_loop, closed_loop, corrected
│   ├── bottleneck.py           ← TODO 4: config_result, paired_ratio, claim_cost
│   ├── capacity.py             ← TODO 5: simulate
│   └── report.py               ← provided
├── solution/perflab/           ← reference solution (instructors; read only after finishing)
├── templates/performance-claim.md
├── tests/                      ← test_perflab (hand-checkable), test_golden, test_relay
└── evidence/                   ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. To check the reference, in bash: `LAB_TARGET=solution python -m pytest -q`.
In PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists
until it is removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's
folder. Until you finish, failing tests stop with `NotImplementedError`; `tests/test_relay.py` passes from the start.

## Steps

### 1. Read the claims (15 min)

Read Chapter 11's sentence about the limiter, ADR-014, `relay-repo/src/relay/service/sharedlimit.py` and
ADR-040. Then run Relay's checks: `cd relay-repo && PYTHONPATH=src python -m pytest -q && python tools/lint.py`
(PowerShell: `$env:PYTHONPATH="src"; python -m pytest -q; Remove-Item Env:PYTHONPATH`).

### 2. The workload model: TODO 1 (35 min)

Implement `build_model` in `workload.py`, then `cd starter && python -m perflab.report workload`. Why is the
test rate set from the busiest minute and not the busiest hour? What does Little's law say about how many
requests are in the service at the peak, and what does it not say?

### 3. Percentiles and intervals: TODO 2 (25 min)

Implement `percentile`, `summarize` and `mean_interval` in `stats.py`. Why nearest rank rather than
interpolation for a latency budget? Why is an interval over five runs not an interval over requests?

### 4. Coordinated omission: TODO 3 (30 min)

Implement the three functions in `omission.py`, then `python -m perflab.report omission`. One stall of one
second: how many samples does the closed loop record for it, and what does its p99 say? Which tool you have
used works like the closed loop?

### 5. Before and after the fix: TODO 4 (50 min)

Implement `config_result`, `paired_ratio` and `claim_cost` in `bottleneck.py`, then:

```bash
python -m perflab.report runs > ../evidence/runs.md
python -m perflab.report stress
python -m perflab.report soak
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 ../evidence/runs.md` instead.
Where did the time go before the fix, and how do you know it was the limiter and not the network? Did 4.21.0's
limiter meet the budget at the test rate? At what rate did it stop? What will the worker's claim cost in a year?

### 6. Measure your own machine (35 min)

```bash
python -m perflab.report live --out ../evidence/my-runs.json --runs 3 --duration 20
cd ../relay-repo && python tools/loadtest.py budgets ../evidence/my-runs.json && cd ../starter
```

Close other heavy programs first, and keep the laptop on mains power. Your milliseconds will differ from
`data/measured/`. Compare ratios and ranks, not values: does the lease configuration still win, by about the
same factor? Record your machine in `templates/performance-claim.md`.

### 7. Worker capacity: TODO 5 (30 min)

Implement `simulate` in `capacity.py`, then `python -m perflab.report worker` and `python -m perflab.report budgets`.
Check one row with Little's law by hand. Why does one worker fail the outage, and why is the longest gap
between passes the number ESC-N09 cares about?

### 8. Write the claim (20 min)

Fill in `templates/performance-claim.md` for the lease limiter: workload, environment, duration, warm-up,
percentiles, intervals and limitations. Then run the workspace audit from
`labs/ch03/L3.1-accountable-workspace/solution/`:
`python -m audit.report --policy ../data/policy.json --as-of 2027-02-19 --fail-on high ../../../ch17/L17.1-load-test-bottleneck/relay-repo`
(0 open, 0 waived).

## Expected evidence

- `evidence/runs.md` and a paragraph naming the bottleneck, the evidence for it and the fix's measured effect.
- `evidence/my-runs.json` and your comparison with the recorded runs.
- A completed `templates/performance-claim.md`.

## Troubleshooting

- `NotImplementedError: TODO n` — expected until you implement TODO n.
- The live run reports errors or very high latency — another program is busy, or a firewall prompt blocked the
  loopback servers; allow Python on private networks only, or rerun. The run never leaves 127.0.0.1.
- Every request takes about 15 ms on Windows — a socket timeout is set somewhere: Windows waits on the system
  timer. `tools/loadtest.py` uses blocking sockets for this reason (see its `call` function).
- Results differ from the chapter — check `LAB_TARGET`, then rerun `python scripts/generate_data.py` and
  `git diff data/`; the generated data must not change. `data/measured/` is fixed and is not regenerated.
- `UnicodeEncodeError` on Windows — set `PYTHONIOENCODING=utf-8`.

## Known limits

One SQLite file on one laptop, two server processes, loopback networking and a Python client. Nothing here
measures a network, a load balancer, PostgreSQL or a real model. The traffic is synthetic. The worker
simulation ignores the escalation pass's own time.

## Cleanup

`tools/loadtest.py` deletes its temporary folders. Delete `evidence/` contents you do not want to keep.

## Rubric (10 points)

| Points | Criterion |
| ---: | --- |
| 2 | Workload model correct (tests pass), with the busiest-minute and Little's-law answers |
| 2 | Percentiles, intervals and the coordinated-omission explanation |
| 3 | Bottleneck named from server-side evidence, fix re-measured with paired ratios, stress knee and soak finding explained |
| 1 | Your own machine's runs compared by ratio and rank |
| 2 | Worker capacity checked by hand, and a complete performance claim |

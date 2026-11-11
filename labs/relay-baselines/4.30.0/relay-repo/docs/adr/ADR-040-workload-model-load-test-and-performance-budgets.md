# ADR-040 — A workload model, an open-schedule load test on the standard library, and performance budgets

Status: accepted
Date: 2027-02-15
Decided by: sam.o (architect of record)
Reviewed by: priya.n (engineering), tomas.b (support, for the worker budget)
Links: CON-4, CON-6, ESC-N09, CON-1
Related: ADR-007, ADR-008, ADR-014, ADR-015, ADR-041
Revisit when: the service runs on the PostgreSQL adapter or behind a real load balancer; the busiest minute
grows past half the test rate; or a load tool is admitted to the mirror. Review by 2027-08-15 in any case.
Supersedes: none.

## Context

Chapter 6 left cross-process behaviour under load untested, and Chapter 11 accepted one database write per
request on the claim that it was "well within a small instance's capacity at non-production volume".
Nothing in the repository could check either statement. CON-4 says no API request waits for the triage
model and the API's p95 stays under one second, but there was no workload, no test and no budget tighter
than CON-4 to say when the service is getting worse. The triage worker had no capacity figure at all, and
ESC-N09 depends on it: the worker runs an escalation pass before every triage call.

## Options considered

### Option A — A workload model from traffic counts, a standard-library open-schedule load test in `tools/`, and budgets in `perf/`

### Option B — Adopt an established load tool (for example Locust, k6 or wrk2) as a development dependency

### Option C — No load test; rely on production monitoring and CON-4

## Decision

Option A.

- `perf/workload.json` is the workload: the busiest hour's mix of journeys, the callers active in it, and a
  test rate of twice the busiest minute of the week of 1 February 2027 (Lab 17.1 derives it; 140 requests a
  second). It is versioned, and a change to it is reviewed like a change to code.
- `tools/loadtest.py` runs the production WSGI application (`relay.service.wsgi.create_app`) in two
  one-request-at-a-time server processes on 127.0.0.1, with a worker process sharing the database. Arrival
  times are drawn in advance (Poisson, fixed seed) and every latency is measured from the request's due time,
  so a stall counts against every request it delays. Warm-up is discarded. Configurations are interleaved run
  by run, and each run records its environment.
- `perf/budgets.json` (relay-perf-budgets-v1): at the test rate, p99 at most 50 ms per request, errors at most
  0.1%, and at most 0.2 limiter write transactions per request; for the worker, a p95 time to suggestion of at
  most 30 seconds with two workers at the busiest hour and in an outage of 300 tickets in ten minutes.
- The deterministic parts are tested with every change (`tests/test_loadtest.py`): the schedule, the mix and
  the limiter's transactions per request at the workload. Latency budgets are checked by `loadtest.py budgets`
  on a stated machine, because they depend on it.
- Merge note for the worker (Chapter 17 does not own `relay/worker/`): add
  `CREATE INDEX IF NOT EXISTS triage_jobs_open ON triage_jobs (status, available_at);` to `queue.py`'s schema.
  Without it `claim` scans every finished job inside `BEGIN IMMEDIATE`, holding the write lock while it reads.

## Consequences

- Chapter 11's claim is now checked: the 4.21.0 limiter met the 50 ms p99 budget at 140 requests a second on
  the reference laptop, and missed it at 280 (Lab 17.1, `perflab.report stress`). ADR-041 removes that limit.
- The test is a laptop test of one SQLite file. It says nothing about network latency, the PostgreSQL adapter,
  or a load balancer, and its milliseconds are the reference machine's. Every claim made from it states the
  workload, environment, duration, warm-up, percentiles and these limits.
- The workload is synthetic until production access logs exist; the budget then moves to real counts.
- The worker budget is a support decision (tomas.b), not a property of the code, and is set at the ticket
  rates above. A slower triage model breaks it before the queue looks unhealthy (Chapter 17's incident).

## Rejected alternatives

### Option B — Adopt an established load tool (for example Locust, k6 or wrk2) as a development dependency
Rejected because: it adds a dependency or a binary to the mirror for a test that the standard library already runs, and the tool would still need Relay's fixture and workload code.
Revisit if: the service is tested over a real network or at rates a Python client cannot generate, when wrk2 or k6 earns a dependency review under ADR-028.

### Option C — No load test; rely on production monitoring and CON-4
Rejected because: CON-4's one-second p95 is far looser than the service's real behaviour, so it would be met long after the bottleneck had used up the headroom.
Revisit if: never on its own; production monitoring (Chapter 16) complements the test and does not replace it.

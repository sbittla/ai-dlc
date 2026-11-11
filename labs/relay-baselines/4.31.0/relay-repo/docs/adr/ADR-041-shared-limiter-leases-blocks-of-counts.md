# ADR-041 — The shared rate limiter leases blocks of ten counts instead of writing once per request

Status: accepted
Date: 2027-02-15
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: CON-3, CON-4, ESC-N09
Related: ADR-014, ADR-015, ADR-031, ADR-040
Revisit when: the PostgreSQL adapter lands (its row locks behave differently); the service runs more than four
processes; or a customer's integration depends on reaching exactly 600 requests in a minute. Review by
2027-08-15 in any case.
Supersedes: the "one transaction per request" part of ADR-014's limiter design.

## Context

4.21.0's `SharedRateLimiter` counted every API request, reads included, in its own `BEGIN IMMEDIATE`
transaction on the database that the worker's queue and escalation pass also write. Chapter 17's load test
(ADR-040) measured it on the reference laptop at 140 requests a second: 2.6 ms of every request's 2.9 ms inside
the application was the limiter (89.3%), and p99 was 33.4 ms. Waiting for the write lock, not counting, is
where the time went. At 280 requests a second p99 passed 50 ms. A token flooding past its limit also cost one
write transaction per refused request.

## Options considered

### Option A — Lease up to ten counts per transaction and spend them from memory; remember a full window until it ends

### Option B — Keep one exact write per request (4.21.0)

### Option C — Move the counters to an in-memory store shared by the processes (for example Redis)

## Decision

Option A.

- A process leases at most ten counts per transaction, and never more than the window has left, so the
  processes together never admit more than 600 a minute.
- Leases end with their window and unused counts are not returned. A token can therefore be refused early, by
  at most (processes - 1) x 9 requests in a window: 9 of 600 with two processes. With one process every decision
  is the exact limiter's (`tests/test_service_sharedlimit.py` checks both).
- Once a window's count reaches the limit, the process remembers it until the window ends, so refused
  requests cost at most one write per process per window (the lease that finds the window full).
- `block=1` keeps the exact behaviour for tests and for anyone who needs it. `transactions` counts the
  limiter's write transactions, and ADR-040's budget caps them at 0.2 per request.

## Consequences

- Re-measured on the same machine and schedule: limiter transactions fell from 0.981 to 0.106 per request, and
  p99 from 33.4 ms to 10.6 ms (paired by run: 0.318 of before, 95% interval 0.237 to 0.399). The 50 ms budget
  now holds at 560 requests a second in the stress test.
- Relay's documented limit stays 600 requests a minute; the possible early refusal of up to 9 is recorded
  here and in the limiter's docstring. Retry-After is unchanged.
- The window-edge burst of up to twice the limit, and the 401-before-count behaviour, are unchanged.
- The write lock is still shared with the worker. The worker's own full-table scan under that lock is the
  next bottleneck as the queue table grows (ADR-040's merge note).

## Rejected alternatives

### Option B — Keep one exact write per request (4.21.0)
Rejected because: the limiter was 89% of the application's time per request and the first thing to break the p99 budget as load doubled.
Revisit if: exact counting becomes a contractual requirement, in which case use exact counting with fewer processes or Option C.

### Option C — Move the counters to an in-memory store shared by the processes (for example Redis)
Rejected because: it adds a service to operate and a dependency to review for a problem a ten-count lease removes, and Relay's eight engineers run one on-call rota (CON-1).
Revisit if: the service needs more than four processes, or several tasks share one limit after the PostgreSQL adapter.

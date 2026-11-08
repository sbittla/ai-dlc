# ADR-007 — Relay as a modular monolith with an asynchronous triage worker

Status: accepted
Date: 2026-11-25
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), lena.k (product)
Links: D3, D5, D7, D8, D9, ESC-N01, ESC-N03, ESC-N04, ESC-N07, ESC-N09, ESC-N10, CON-1, CON-2, CON-4
Revisit when: triage or escalation gets its own team and on-call rota; or Relay runs more than one service process and the shared database becomes the limit; or one module needs scaling the others cannot share. Review by 2027-11-25 in any case.
Supersedes: none. It records the May 2026 decision on triage that was taken in a meeting and never written down.

## Context

Relay 4.17.2 is a library with JSON views. Chapter 4's approved PRD for escalation rules needs a server that
enforces rule permissions (ESC-N03) and a background process that fires timed steps (ESC-N09). Ticket triage,
built in Chapter 2, needs a place to run that does not make API callers wait for a model.

The drivers are the PRD's ten NFRs and six constraints from Relay's facts, catalogued as `relay-drivers-2026.11`
and scored by sam.o (Lab 6.1, `data/drivers.json`). The ones that decide this ADR: one platform on-call rota for
eight engineers (CON-1); the daily deploy train (CON-2); no API request waiting for the model, whose p95 latency
was 4.12 s in Chapter 2's evaluation (CON-4); a flood cap counted across all rules (ESC-N04, D7); suggestions that
never act alone (ESC-N01, D3); no task content outside Relay (ESC-N07); and no paid messaging (ESC-N10, D5).

## Options considered

### Option A — Modular monolith with an asynchronous triage worker

One codebase, one artifact, two process types: `relay.service` (HTTP) and `relay.worker`. One database; each
module owns its tables. The service queues triage jobs in `triage_jobs` and returns 202; the worker calls the
model, validates the answer and records a suggestion.

### Option B — Microservices with a message broker

An API gateway and four services (tasks, escalation, triage, notification), each with its own database,
exchanging events through a managed broker.

### Option C — Modular monolith with synchronous triage in the request

As Option A, but the service calls the model while the caller waits.

### Option D — Serverless function for triage

As Option A for everything except triage, which runs as a cloud function triggered by a managed queue.

## Decision

Option A. Scored against `relay-drivers-2026.11`, Option A has 75 of 93 weighted points and Option B 52 of 93.
No single weight from 0 to 5 changes that ranking. Counted from the option files, an escalation step needs 2
internal components in Option A and 7 in Option B; at 99.9% each, independently, that is 86.4 against 301.5
minutes per 30 days in which steps cannot fire. Options C and D were not scored, for the reasons below.

## Consequences

- One artifact ships on the daily train. A change that spans modules is one reviewed change.
- No request waits for the model. A slow or failing model delays suggestions, not the API.
- Delivery is at least once. Jobs carry idempotency keys; a worker whose lease expired cannot overwrite a result.
- Module boundaries are enforced by tests, not by processes: `tests/test_architecture.py` rules AR1 to AR5. They
  see static imports only.
- Both processes use one database role, so a compromised worker can reach every table. Owner: sam.o; separate
  roles when the deployment exists (Chapter 11).
- The rate limiter counts per process. It is exact for one service process and must move to shared storage
  before there are two.
- A bad change to any module ships with all the others. The eval gate (Chapter 7) and the test suite are the
  controls; a rollback reverts the whole artifact.

## Rejected alternatives

### Option B — Microservices with a message broker
Rejected because: one rota of eight engineers would run five deployables, four databases and a broker; the flood cap across all rules would need a shared counter; task content would cross the broker; and the broker adds a paid service to what escalation calls, against ESC-AC31.
Revisit if: triage or escalation gets its own team and rota (Lab 6.1's five-teams scenario shows Option B ahead under those assumptions).

### Option C — Modular monolith with synchronous triage in the request
Rejected because: every ticket submission would wait for the model, whose p95 was 4.12 s in Chapter 2, against the 1-second API budget in CON-4, and a model outage would become an API outage.

### Option D — Serverless function for triage
Rejected because: it adds a second deployment model, a managed queue and a second set of credentials for one module, while retries, the person's queue and stall detection still have to be built.
Revisit if: triage traffic becomes so uneven that idle worker processes cost more than the second platform.

## Fitness functions

`tests/test_architecture.py` runs in the required `tests` check: AR1 domain modules import neither the service nor
the worker; AR2 the service imports only `relay.worker`, never its submodules; AR3 the worker never imports the
service; AR4 only the service imports network modules; AR5 standard library only.

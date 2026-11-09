# ADR-007 — Relay as a modular monolith with an asynchronous triage worker

Status: accepted
Date: 2026-11-25
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), lena.k (product)
Links: D3, D5, D7, D8, D9, ESC-N01, ESC-N03, ESC-N04, ESC-N07, ESC-N09, ESC-N10, CON-1, CON-2, CON-4, CON-6
Revisit when: triage or escalation gets its own team and on-call rota; or Relay runs more than one service process and the shared database becomes the limit; or one module needs scaling the others cannot share. Review by 2027-11-25 in any case.
Supersedes: none. It records the May 2026 decision on triage that was taken in a meeting and never written down, and extends it to escalation rules.

## Context

Production Relay already has an HTTP API (600 requests per minute per token) and webhooks, and since May 2026
ticket triage has run as a background worker inside the main application. That choice was made by a three-person
sub-team in a meeting and recorded nowhere. Chapter 3's teaching snapshot (4.17.2) is a library with JSON views;
Relay 4.19.0 brings the service layer and the triage worker into the snapshot, built to this decision.

The new need is escalation rules (Chapter 4's PRD v1.0). They need permissions enforced on the server (ESC-N03), a
background evaluator that fires timed steps (ESC-N09), and a flood cap counted across all rules (ESC-N04, D7).

The drivers are the PRD's ten NFRs and six constraints from Relay's facts, catalogued as `relay-drivers-2026.11`
and scored by sam.o (Lab 6.1, `data/drivers.json`). The ones that decide this ADR: one platform on-call rota for
eight engineers (CON-1); the daily deploy train (CON-2); no API request waiting for the model, whose p95 latency
was 4.12 s in Chapter 2's evaluation of a simulated model (CON-4); suggestions that never act alone (ESC-N01, D3);
no task content outside Relay (ESC-N07); and no paid messaging (ESC-N10, D5).

## Options considered

### Option A — Modular monolith with an asynchronous triage worker

One codebase, one artifact, two process types: `relay.service` (HTTP) and `relay.worker`. One database; each
module owns its tables. The service queues triage jobs in `triage_jobs` and returns 202; the worker takes each job,
gets a triage answer, validates it and records a suggestion. In the 4.19.0 snapshot the triage call is simulated
in-process; the production model adapter is a separate decision (see Consequences).

### Option B — Microservices with a message broker

An API gateway and four services (tasks, escalation, triage, notification), each with its own database,
exchanging events through a message broker that the team runs itself.

### Option C — Modular monolith with a separate triage service

As Option A for tasks and escalation; triage moves into its own deployable service with its own database, called
by Relay's service over the internal network.

### Option D — Modular monolith with synchronous triage in the request

As Option A, but the service calls the model while the caller waits.

### Option E — Serverless function for triage

As Option A for everything except triage, which runs as a cloud function triggered by a managed queue.

## Decision

Option A. Scored against `relay-drivers-2026.11`, Option A has 75 of 93 weighted points, Option C 68 and Option B
52. No single weight from 0 to 5 changes the ranking. Against Option C the lead is narrow: at least 3 one-point
score changes would reverse it, so the scores on CON-1, CON-2 and ESC-N01 were reviewed by aisha.r and priya.n
before acceptance. Against Option B, at least 8 would be needed.

Counted from the option files, an escalation step needs 2 internal components in Options A and C and 7 in Option
B; at 99.9% each, independently, that is 86.4 against 301.5 minutes per 30 days in which steps cannot fire.
Options D and E were considered but not scored, for the reasons below.

## Consequences

- One artifact ships on the daily train. A change that spans modules is one reviewed change.
- No request waits for the model. A slow or failing model delays suggestions, not the API.
- Delivery is at least once. Jobs carry idempotency keys scoped to a workspace; a worker can complete or fail a
  job only while it holds the job's lease.
- Module boundaries are enforced by tests, not by processes: `tests/test_architecture.py` rules AR1 to AR5. They
  see static imports only.
- In 4.19.0 only the service touches the network. The production model adapter, email and webhook delivery will
  each be one module, allowed network access by its own ADR and a one-line change to AR4 (Lab 6.2's FF004).
- Both processes use one database role, so a compromised worker can reach every table. Owner: sam.o; separate
  roles when the deployment exists (Chapter 11).
- The rate limiter counts per process in fixed one-minute windows. It must move to shared storage before there
  are two service processes.
- A bad change to any module ships with all the others. The eval gate (Chapter 7) and the test suite are the
  controls; a rollback reverts the whole artifact.

## Rejected alternatives

### Option B — Microservices with a message broker
Rejected because: one rota of eight engineers would run five deployables, four databases and a broker; the flood cap across all rules would need a shared counter; task content would cross the broker; and the broker would join the services escalation calls, so ESC-AC31 would need amending.
Revisit if: several product teams each need to own and release a part of Relay on their own rota (Lab 6.1's five-teams scenario).

### Option C — Modular monolith with a separate triage service
Rejected because: it adds a second pipeline, database and runbook for one rota, and moves the suggestion-only rule to a contract between two codebases, for independent scaling that CON-6 weights at 1.
Revisit if: triage gets its own team and rota, or its load needs scaling the monolith cannot share; Lab 6.1's five-teams scenario puts Option C first.

### Option D — Modular monolith with synchronous triage in the request
Rejected because: every ticket submission would wait for the model, whose p95 was 4.12 s in Chapter 2, against the 1-second API budget in CON-4, and a model outage would become an API outage.
Revisit if: a model's p95 latency, measured on Relay's own traffic, falls well under the 1-second budget and its provider's availability exceeds Relay's.

### Option E — Serverless function for triage
Rejected because: it adds a second deployment model, a managed queue and a second set of credentials for one module, while retries, the person's queue and stall detection still have to be built.
Revisit if: triage traffic becomes so uneven that idle worker processes cost more than the second platform.

## Fitness functions

`tests/test_architecture.py` runs in the required `tests` check: AR1 domain modules import neither the service nor
the worker; AR2 the service imports only `relay.worker`, never its submodules; AR3 the worker never imports the
service; AR4 only the service imports network modules; AR5 standard library only.

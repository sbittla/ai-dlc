# ADR-049 — Agents run as durable queue workers, with a dead-letter state and an effect ledger keyed by the business object

Status: accepted
Date: 2027-03-15
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), tomas.b (support operations)
Links: ESC-N01, CON-1, CON-5, CON-6
Related: ADR-007, ADR-011, ADR-024, ADR-026, ADR-027, ADR-036
Revisit when: the PostgreSQL adapter lands (the queue, the ledger and the run store move with it); more than
four agent kinds or more than ten workers share the queue; or a workflow engine is adopted elsewhere in the
company. Review by 2027-09-15 in any case.

## Context

From 1 to 9 March 2027 a support-operations pilot ran a refund assistant as one long-lived script on one virtual
machine, outside Relay's agent registry. Its queue delivered at least once; a thread whose run passed the queue's
60-second visibility timeout lost its message to another thread while still working, and the billing webhook
sent some events twice. Every delivery ran to the end and called the payment provider with no idempotency key.
Lab 18.1's replay of its 190 deliveries: 151 refunds for 130 eligible charges, 21 duplicates on 16 charges,
$2,928 refunded twice (15 from visibility timeouts, 6 from webhook duplicates). Chapter 10's run journal would
not have helped: each delivery would have been a new run with its own keys.

Relay's own agents need the same answer before they run anywhere but CI: the spec-to-PR helper (ADR-027) and
any later agent. Chapter 6's triage queue (ADR-007) has the right shape but holds one model call per job, not a
run that can take minutes, wait for an approval and spend money.

## Options considered

### Option A — An agent job queue in Relay's database, a run per job on the ADR-024 runtime, and an effect ledger

### Option B — A workflow engine service (for example Temporal) that owns state, retries and timers

### Option C — A managed queue's visibility timeout and redrive policy, with workers that hold no state of their own

### Option D — A supervising agent that watches the other agents' runs and retries what failed

## Decision

Option A.

- `relay.agentops.jobs.AgentJobQueue`: jobs deduplicated on (kind, business key), so a repeated delivery is
  the same job; fenced leases (a new token per claim) extended by heartbeats between steps; retries with full
  jitter and a provider's Retry-After as a floor; a `dead` state with a reason for attempts exhausted, poison
  payloads, expired leases and revoked agents, brought back only by a person who presents their own proof
  (`redrive`), with a reason; cancellation between steps; approval waits that park the job without spending an
  attempt, woken by `decide_and_wake` once the gate accepts a person's decision.
- A business key names the work and its version: a reopened task or a request made again after a cancellation gets
  a new generation (`spec-to-pr:RLY-2301@2`), because a done or cancelled job keeps its key for ever.
- `relay.agentops.worker`: one run per job, its request key the job's kind and key, resumed from the run store
  by any worker; a circuit breaker per dependency, consulted before a claim so jobs wait instead of failing. A
  half-open trial that ends in a poison payload, a cancellation or a lost lease gives its slot back; an
  unclassified error counts as a failure. The worker heartbeats before it writes a run's checkpoint, so a worker
  that lost its job writes nothing more to the run; the lease must exceed the longest step (sandbox timeout plus
  model timeout), because the step in progress is still journalled.
- `relay.agentops.effects.EffectLedger`: every effect outside Relay goes through it under a natural key (for
  example `pr:<task>`, `refund:<charge>`), once per key across runs, the key passed to the provider as its
  idempotency key; a started effect is repeated only if the provider deduplicates, and only within the
  provider's key window (24 hours for the helper's pull requests): past it, a person checks.
- **Delegation (designed, not built).** A job that acts for a person will carry a grant signed by the person
  issuer at enqueue: the person, the agent, the task, the job's key and an expiry under 24 hours. The queue
  stores it; `run_agent` verifies it before each run and the session exchanges it, so no producer can name a
  person who did not ask. Until it exists, `enqueue` records whatever `on_behalf_of` the producer names, and the
  queue must be reachable only from Relay's own service (owner aisha.r with sam.o, by 2027-05-31).
- A deterministic step stays deterministic: deciding that a charge was taken twice is a query, not an agent.

## Consequences

- Lab 18.1's replay of the pilot's deliveries: business-key deduplication alone leaves 15 duplicate refunds,
  heartbeats alone 6, the ledger alone 0, and dedup with heartbeats 0. A worker that dies mid-run still loses
  its lease, so the ledger is the layer that covers every cause (drill F1).
- Drills F0 to F8 pass on 4.30.0: restart, duplicate delivery, timeouts to the dead-letter state, a rate limit
  that opens the breaker, a sandbox refusal, a kill-switch trip, a cancellation and a poison payload.
- A dead job's run stays resumable: redriving it continues the same run with its budget.
- Breakers are per process: a pool of N workers can send up to N times the threshold of failing calls, and N trial
  calls per cool-down. Acceptable for a few workers; a larger pool keeps the breaker's state in the database.
- Not built in 4.30.0, each with an owner: the worker process itself (nothing in `src/` starts an `AgentWorker`;
  a deployed worker needs an `ecs-task` registry entry and role; sam.o, 2027-05-31); the service route that calls
  `decide_and_wake` (priya.n, 2027-04-30); the person-proof signature verifier that `redrive` and the gate rely on
  (sam.o, Chapter 13's review); a 30-day retention or redaction for step results in the run journal (sam.o,
  2027-04-30).
- The queue shares the SQLite write lock with the service and the triage worker until the PostgreSQL adapter.
- Until the helper's own GitHub App is installed (Chapter 12's open item) and the PostgreSQL adapter exists, these
  workers run in tests, labs and local runs only: the cloud environment carries no traffic yet.
- Nothing alerts on the dead-letter state yet: an alert rule on dead agent jobs belongs in
  `infra/monitoring/alerts.json` (owner sam.o, by 2027-04-16).

## Rejected alternatives

### Option B — A workflow engine service (for example Temporal) that owns state, retries and timers
Rejected because: it gives durable steps and timers Relay needs, but adds a cluster for eight engineers to run on one rota (CON-1), and Relay's run store already records every step.
Revisit if: Relay needs timers longer than a day, more than four agent kinds, or the company adopts an engine elsewhere.

### Option C — A managed queue's visibility timeout and redrive policy, with workers that hold no state of their own
Rejected because: a visibility timeout is a lease without fencing or business keys, which is exactly how the pilot refunded the same charges twice.
Revisit if: Relay moves to a managed queue for scale; the ledger and the business keys stay in Relay's database.

### Option D — A supervising agent that watches the other agents' runs and retries what failed
Rejected because: retrying, deduplicating and dead-lettering are rules code can state and test, and a model making those decisions adds cost and a new way to fail.
Revisit if: a failure class appears that no rule can recognise from the journal and the queue's events.

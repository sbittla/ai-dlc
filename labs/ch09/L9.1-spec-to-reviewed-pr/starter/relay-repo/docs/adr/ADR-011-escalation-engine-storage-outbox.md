# ADR-011 — The escalation engine's tables, and an outbox instead of sending

Status: accepted
Date: 2026-12-02
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: D7, D9, ESC-N03, ESC-N04, ESC-N07, ESC-N10, CON-1, CON-2
Revisit when: delivery adapters for email or webhooks are built (each needs its own ADR and a one-line change to FF004); or the outbox grows faster than the adapters drain it; or escalation moves out of the monolith (ADR-007's revisit conditions).

## Context

Spec ESC-SPEC-1 1.1.0 needs rules stored with an audit trail (ESC-N03), steps that fire at most once (D9),
escalation emails capped per target across all rules (ESC-N04, D7), and emails and signed webhook events
(ESC-R09). ADR-007 keeps one database with tables owned by modules, and FF004 allows network access only in
`relay.service` until each adapter has its own ADR. The worker, which ADR-007 says will run evaluation passes,
is unchanged in 4.20.0 so that work on the deployment can proceed on the same baseline.

## Options considered

### Option A — Engine-owned esc_ tables in Relay's database, and an outbox table that delivery adapters drain

### Option B — The engine sends email and webhook requests itself during the pass

### Option C — Store rules and state in the existing task store

## Decision

Option A. `relay/escalation/store.py` owns seven tables, all prefixed `esc_`. `run_pass` records a fired step and
writes its messages to `esc_outbox` in one transaction, so a step is never recorded without its messages or sent
twice. The flood cap counts outbox emails in the same transaction. The worker will call `run_pass` on each loop;
that call is a worker change with its own review.

## Consequences

- The escalation package stays free of network modules (AR4, SEC-05); only `store.py` imports `sqlite3`. The new
  modules join DOMAIN in `tests/test_architecture.py`.
- The outbox is at-least-once for adapters: each row has a unique dedupe key, and adapters must be idempotent.
- The webhook secret signs bodies and is never stored; the outbox holds the signature.
- Until adapters exist, nothing leaves Relay. The 4.20.0 snapshot proves message content, not transport.
- Audit entries are kept in `esc_audit`; the 400-day retention is the deployment's job (ESC-N03).

## Rejected alternatives

### Option B — The engine sends email and webhook requests itself during the pass
Rejected because: it puts network calls in a domain module against AR4 and FF004, makes a slow provider stall every pass, and loses the single transaction between firing a step and recording its messages.
Revisit if: never in the domain; a delivery adapter module with its own ADR is the place for sending.

### Option C — Store rules and state in the existing task store
Rejected because: it makes the task store's table carry escalation columns that another module owns, which ADR-007's one-owner-per-table rule forbids and which would couple two modules' migrations.
Revisit if: tasks gain a general activity log that escalation can append to through the task module's interface.

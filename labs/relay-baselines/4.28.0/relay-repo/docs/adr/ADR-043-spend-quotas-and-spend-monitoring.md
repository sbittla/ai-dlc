# ADR-043 — Daily spend quotas per user, agent, workspace and feature, and a cost-per-success monitor

Status: accepted
Date: 2027-02-17
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), tomas.b (support), lena.k (product)
Links: ESC-N01, CON-3, CON-1
Related: ADR-014, ADR-020, ADR-024, ADR-041, ADR-042
Revisit when: the PostgreSQL adapter lands; a customer-facing AI feature is added; or the first quota refusal
in production is investigated. Review by 2027-08-17 in any case.
Supersedes: none.

## Context

Relay's rate limit bounds how often a token may call, not what its calls cost. At 600 requests a minute one
token can queue 36,000 triage jobs an hour, each a paid model call; Lab 17.2 puts that hour at about $165 on
the routed configuration. Chapter 10's run budgets bound one agent run, but nothing bounds a feature's daily
spend or a caller's share of it. And in January nobody noticed a tripled cost per success for a month,
because spend was read from the monthly invoice.

## Options considered

### Option A — Daily quotas in a shared ledger (`relay.routing.SpendQuota`), reserved before the work and settled after, plus a daily cost-per-success monitor

### Option B — Rely on the provider's spend limit on the API key

### Option C — Rely on the rate limit alone

## Decision

Option A.

- The service reserves one hard-route call's ceiling per ticket against `user:<id>` and
  `workspace:<ws>` before it queues the ticket, keyed by the idempotency key, and answers 429 with Retry-After
  until UTC midnight when either would pass its daily limit. The worker reserves each call's ceiling against
  `agent:triage-worker` and `feature:triage` and settles the actual cost after the call. A refused call is
  retried with backoff and then handed to a person; it never becomes a guessed label (ESC-N01).
- Starting limits: user $3.00, workspace $60.00, agent $80.00 and feature $100.00 a day, set in configuration.
  A principal of a kind with no limit is refused. Every reservation, refusal and settlement is a row in
  `spend_events`; refusals name the principal and never the ticket.
- `SpendMonitor` checks cost per suggestion delivered daily over a three-day window against the approved
  baseline with Chapter 7's 25% tolerance, and a daily spend ceiling. Cost per correct triage needs labels
  that arrive late (confirmations and the weekly sample), so it is checked weekly. `SpendQuota.refusal_counts`
  counts refusals per hour by principal kind.
- Merge note for Chapter 16's alert rules (`infra/monitoring/alerts.json`), proposed text:
  `{"id": "AL-009", "title": "Spend quota refusals", "metric": "relay.routing.quota_refusals.1h",
  "op": ">=", "threshold": 50, "severity": "page", "category": "security", "source": "ADR-043",
  "runbook": "infra/runbooks/incident-response.md"}`, with the metric labelled by principal kind only.
  Nothing pages on a refusal until that rule and the hooks are merged.
- Merge notes (Chapter 17 owns `relay.routing` only): the service hook is the five lines in
  `tests/routing_hooks.py` before `enqueue` in `RelayApp.create_job`, with `quota` and `triage_estimate_usd`
  constructor arguments; the worker hook is `MeteredTriage` moved to `relay/worker/metered.py`, wrapping the
  triage client in `relay/worker/__main__.py` (and, after Chapter 12's 4.26.0, the summarizer too, which is a
  second paid call). Each call reserves under its own ref. `tests/test_routing_hooks.py` runs both on the
  real code. Until they merge, no quota is enforced anywhere in Relay.

## Consequences

- The user quota bounds tickets, not dollars: a ticket that retries on the hard route can cost up to three
  ceilings, and user reservations are not settled. The agent and feature quotas, which settle actual costs,
  bound the money.
- In Lab 17.2's simulated hour, one stolen token is held to 125 queued tickets and the real users lose none.
  Twenty stolen tokens reach the workspace limit in about four minutes, and then real users of that workspace
  are refused too (18 of 140 accepted): a workspace limit turns abuse into an outage for that workspace. That
  is the intended trade, and AL-009, once merged, is what pages the on-call.
- Reserving the ceiling rather than the mean makes a user's limit about five times stricter than the mean
  spend; an attacker who writes hard-looking tickets can steer the router to the hard route, so attack spend
  tends to the ceiling.
- The ledger is another write on the shared database, one per queued ticket and two per model call: far fewer
  than the limiter's, and inside ADR-040's budget.
- The provider's own key limit stays as a second layer.

## Rejected alternatives

### Option B — Rely on the provider's spend limit on the API key
Rejected because: it stops every feature sharing the key at once, cannot tell one caller from another, and arrives as an outage rather than a refusal.
Revisit if: never on its own; keep it as the outer layer.

### Option C — Rely on the rate limit alone
Rejected because: the rate limit permits 36,000 queued tickets an hour per token, which is a cost the support budget cannot carry.
Revisit if: triage stops costing money per call, for example on a fixed-price self-hosted model.

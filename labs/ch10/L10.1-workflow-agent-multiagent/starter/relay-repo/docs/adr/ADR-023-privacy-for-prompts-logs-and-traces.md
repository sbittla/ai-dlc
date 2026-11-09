# ADR-023 — Minimize personal data in prompts, logs and traces; redact what remains; set short retention

Status: accepted
Date: 2026-12-22
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), lena.k (product), the data protection officer
Links: ADR-021, ADR-014, Chapter 5 (data classification), Lab 14.2 (DPIA)
Revisit when: the DPIA is reviewed; or the model provider's data-use terms change; or Relay serves a region
outside the current one. Review by 2027-06-22 in any case.
Supersedes: none.

## Context

The leaked debug log held more than a token. It held the response body of a ticket listing: six requester
email addresses and six phone numbers, kept with the CI run's logs (Lab 14.1, `report privacy`). Support
tickets are written by people and contain whatever they choose to write. Before this decision, Relay's traces
of model calls kept full prompts and responses with no retention limit, and nobody had listed where personal
data in agent workflows went.

## Options considered

### Option A — Minimize first: no bodies in logs or the audit trail; prompts carry only the fields a task needs; traces redacted and kept 30 days

### Option B — Keep everything, encrypted, for 400 days, and rely on access control

### Option C — Redact everything with a pattern list and keep it

## Decision

Option A. Logs and the audit trail never contain request or response bodies, headers or tokens. Triage
prompts carry the ticket's subject and body, not the requester's name, email or phone; those stay in Relay's
store. Model-call traces keep the prompt version, the model, timings, token counts and a redacted excerpt, for
30 days. Everything bound for a log passes through `relay.audit.redact`, which replaces credentials, email
addresses and phone numbers with typed markers and counts them. Debug logging of HTTP clients is off in CI and
cannot be turned on by a flag in a workflow file. Lab 14.2's DPIA records each flow, its purpose, retention and
residency.

## Consequences

- Redaction is a second layer. It finds the formats it lists; a name in free text passes through. That is why
  minimization comes first and why traces are short-lived.
- Investigations lose prompt bodies after 30 days. The audit trail keeps who did what for 400 days.
- Relay 4.23.0 has no trace store of its own yet. These rules bind the one that observability work adds later
  (Chapter 16), and the model provider's own logging settings, which are recorded in the DPIA.
- Prompts still contain ticket text, which may contain personal data; the model provider processes it under
  its data-use terms, which the DPIA records and the data protection officer reviews.

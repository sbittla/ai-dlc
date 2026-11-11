# ADR-021 — A hash-chained, anchored audit trail of agent actions, with no prompt or response bodies

Status: accepted
Date: 2026-12-21
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), lena.k (product)
Links: ADR-020, ADR-022, ADR-023, Chapter 1 (the promised audit trail)
Revisit when: Relay's product audit log and this trail are merged; or a regulator or customer contract sets a
different retention; or the anchor store moves to the log-archive account. Review by 2027-12-21 in any case.
Supersedes: none.

## Context

During the incident (ADR-020), Relay's request log recorded a token identifier and a source address for each
call, and nothing else about who acted. Of 2,907 calls by non-human identities in the six weeks reconstructed
in Lab 14.1, none names an agent and none names a person. The logs could be edited by anyone who could write
them, and nothing would show it.

## Options considered

### Option A — One record per agent action, hash-chained, with the head copied hourly to a separate append-only store

### Option B — Structured application logs with the agent id added, in the existing log group

### Option C — Full request and response capture for every agent call, for complete forensics

## Decision

Option A, in `src/relay/audit/trail.py`. Each record holds: the agent, its owner, the person it acted for, the
credential's id, the action, the resource, the outcome, a network label, a small redacted `detail` (such as a
row count), the previous record's hash and its own. Prompt and response bodies are never recorded (ADR-023).
Records go to `/relay/nonprod/agent-audit`; the chain's head is copied to
`/relay/nonprod/agent-audit-anchors` at the end of every hour that has records. Calls to a model are recorded
with the prompt's version and SHA-256 hash, never its text. Both keep 400 days, matching the Business plan's audit log. Relay's
workload roles can create streams and put events there and cannot delete anything.

## Consequences

- An edited or deleted record breaks the chain where it happened. An edit whose later hashes were all
  recomputed passes the chain and fails the next anchor; so does a cut tail. Lab 14.1 shows all four cases.
- Records written after the last anchor can be cut without detection. The hourly interval bounds that window;
  a shorter one costs more writes.
- The anchor group sits in the same account as the trail, so the platform's apply role could delete both. A
  subscription that copies anchors to the landing zone's log-archive account is planned (owner sam.o).
- The trail answers who did what, for whom, from where. It does not answer what a model was told or said;
  investigations that need that use the 30-day trace store (ADR-023).

## Rejected alternatives

### Option B — Structured application logs with the agent id added
Rejected because: anyone who can write the log group can change history without trace, and application logs
mix agent actions with everything else.
Revisit if: the log platform offers immutable, verifiable storage that the team can query as easily.

### Option C — Full request and response capture
Rejected because: it copies personal data from tickets into a 400-day store, the opposite of minimization, and
makes the audit trail itself the most valuable thing to steal.
Revisit if: a specific investigation needs bodies, and then only in the trace store, for that agent, for a
bounded time, with the data protection officer's agreement.

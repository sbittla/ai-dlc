# ADR-051 — The registry's live state moves to the shared database; the service verifies and audits every agent request

Status: accepted
Date: 2027-03-17
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N03, CON-1, CON-3
Related: ADR-020, ADR-021, ADR-022, ADR-038, ADR-049
Revisit when: the PostgreSQL adapter lands; agent tokens move to asymmetric signatures (ADR-020); or agents need a
route other than reading a task. Review by 2027-09-17 in any case.

## Context

Chapter 14 kept each agent's enabled flag and epoch in memory (ADR-020) and deferred two hooks: the service must
verify an agent's token on every request and write an audit record for each. Chapter 16's monitor routes DR-001
and DR-003 to an automated kill-switch trip (ADR-038) but could not trip anything, because no process could see
another's registry. In production the service, every worker and the monitor are separate processes.

## Options considered

### Option A — A table of live registry state in Relay's database, read on every verification with no cache

### Option B — Keep the state in memory and broadcast trips to every process

### Option C — Cache verification results for a short time in each process

## Decision

Option A.

- `relay.agentops.registry_state.SharedRegistry`: the reviewed `governance/agents.json` says who each agent is;
  the table `agent_registry_state` holds `enabled`, `epoch`, `tripped_at` and the current subject. Every read
  goes to the table. A trip increments the epoch in SQL, so two simultaneous trips both count.
- `relay.agentops.gateway.AgentGateway`, wired by `relay.service.wsgi` when `RELAY_AGENT_TOKEN_KEY` is set:
  agent tokens are verified on every request for the route's scope, rate limited per agent, and every request
  is written to the audit trail, refusals included. Agents may read one route in 4.30.0 (a task, with
  `tasks:read:<team>`). Without the key, an agent token is unknown to the service and refused (fail closed).
- `relay.service.monitor --registry --db --trail` trips DR-001/DR-003's agent through the shared state when
  `RELAY_AUTOMATION` is on and the run is not a dry run; a detection group that is not an agent is recorded and
  not tripped.

## Consequences

- Lab 18.1's drill F6: the monitor's trip, in another process, was refused at the helper's next tool call; the
  job went to the dead-letter state as `revoked`. A trip does not interrupt a step already running; the runbook
  still stops running tasks.
- Chapter 14's deferred hooks and Chapter 16's automated trip are closed in code. None is live in the cloud
  environment, which carries no traffic until the PostgreSQL adapter.
- Every agent request now costs one read of the state table; at Relay's volume this is far below the limiter's
  write cost measured in ADR-040.

## Rejected alternatives

### Option B — Keep the state in memory and broadcast trips to every process
Rejected because: a process that misses the broadcast, or starts after it, accepts a revoked token, and nothing records that it did.
Revisit if: verification moves into a separate identity service with its own durable store.

### Option C — Cache verification results for a short time in each process
Rejected because: Chapter 14's first drill showed a 300-second cache delaying revocation to 210 seconds, past the 60-second requirement.
Revisit if: the state table's read cost shows in ADR-040's budgets; then a cache of at most a few seconds, measured against time to revoke.

# ADR-022 — Behavioural detection rules per agent identity, and a kill switch that revokes within 60 seconds

Status: accepted
Date: 2026-12-22
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ADR-020, ADR-021, Chapter 16 (alert delivery and incident response)
Revisit when: a drill misses the 60-second requirement; or false alarms exceed one a week per rule; or the rules
move into a managed detection service. Review by 2027-06-22 in any case.
Supersedes: none.

## Context

The leaked token was used on 14 days over three weeks. Each night's calls differed from the harvester's in plain
ways: a new network, export jobs the harvester never started, and more rows in an hour than it ever read. No
rule looked. Lab 14.1 replays the six weeks with the rules below: the first alert comes 2 minutes 50 seconds
after the first misuse, against 20 days and 13 hours in the incident.

## Options considered

### Option A — Per-identity baselines (28 days) with four rules, evaluated every 5 minutes, and an automated kill switch for high severity

### Option B — Fixed global thresholds on export volume, with paging only

### Option C — A model-based anomaly score over all agent activity

## Decision

Option A. `infra/detection/rules.json` (agent-detection-v1): DR-001 export starts in an hour above the larger
of 3 and three times the identity's baseline maximum; DR-002 a network label the identity has not used; DR-003
rows read in an hour above the larger of 2,000 and three times the baseline maximum; DR-004 any break-glass
session. DR-001 and DR-003 trip the kill switch automatically. The kill switch (`src/relay/audit/killswitch.py`,
`infra/runbooks/kill-switch.md`) disables the identity and moves its epoch in Relay, attaches a deny-all policy
to its cloud role, and stops its running tasks or workflow runs. Only two people can restore it.

## Consequences

- The rules see what the baseline makes unusual, not intent. Lab 14.1's seeded case D01, a stolen token used
  from a GitHub-hosted runner at the harvester's own volume, is missed by all four. Short-lived, federated
  tokens (ADR-020) are the control for that case, not detection.
- One false alarm in the replay's three weeks: an approved analytics backfill. Because DR-001 trips the switch
  automatically, it would have stopped analytics-sync. Approved bulk work is therefore announced with its
  change ticket, and the on-call suppresses the rule for that identity and window, which is itself recorded.
- DR-001's floor of three lets a single export a night pass on an identity that never exported (seeded case
  D01). A rule for an identity's first use of an action would catch D01's first export; it is on the backlog
  (DR-005), with its own false-alarm measurement first.
- Revocation is only as fast as the slowest consumer. In the first, simulated drill, a gateway that cached
  token checks for 300 seconds kept accepting a token for 210 seconds after the alert; every consumer now
  verifies every request (Lab 14.1, DRILL-1 and -2).
- The drills simulate Relay's side with an assumed 4-second trip delay, and assume the cloud and GitHub sides
  (51 seconds for an agent with a role). The requirement is met by the design on those assumptions; it is not
  yet a measurement, and a live drill must replace each assumption.
- An agent with a cloud role is restored only under a new role, or once its old credentials can have expired:
  credentials copied before the trip can still sign `sts:GetCallerIdentity`, which no deny policy stops. Signed
  identity requests carry Relay's audience inside the signature and must be fresh, so a request signed for
  another service, or long ago, cannot be replayed.
- The kill switch scales an ECS agent's services to zero before stopping its tasks, and revokes its GitHub App
  installation tokens. It cannot recall secrets the agent has already read or close connections it holds;
  those end when its tasks stop, and a secret it may have read is rotated.

## Rejected alternatives

### Option B — Fixed global thresholds
Rejected because: a threshold high enough for the analytics export never fires on the harvester's token,
which had never exported anything.
Revisit if: Relay has too few agents for per-identity baselines to be stable.

### Option C — A model-based anomaly score
Rejected because: the team could not explain or test its alerts, and Chapter 7's evaluation discipline would
need a labelled set of agent incidents that does not exist yet.
Revisit if: the seeded cases grow into a labelled set large enough to evaluate one.

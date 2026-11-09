# ADR-017 — The worker runs the escalation evaluation pass on every loop

Status: accepted
Date: 2026-12-10
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N09, D9, CON-1
Related: ADR-007, ADR-011
Revisit when: escalation passes need their own process or schedule (for example a pass that takes longer than the poll interval); or Chapter 16's runtime checks need a separate heartbeat for the evaluator.

## Context

ADR-011 recorded that "the worker will call `run_pass` on each loop" as a separate, reviewed change. Until then no
escalation step fires in a running Relay: only tests call `run_pass`. ADR-007 gives Relay one worker process type,
and AR3 forbids the worker from importing `relay.service`, where the workspace's projects are loaded today.

## Options considered

### Option A — The triage worker runs a pass before each claim, with projects read from the directory file

### Option B — A second process type, `relay.escalator`, with its own loop

### Option C — The service runs a pass on each request

## Decision

Option A. `relay.worker.escalation.EscalationPasses` calls `run_pass` through `relay.escalation`'s public interface
(new rule AR7) at the worker's clock time. `Worker.run_once` runs it first; then it writes the heartbeat and claims
a triage job as before. If the pass raises, it is rolled back, counted as `escalation_failed`, logged, and the
heartbeat is not written, so a worker whose evaluator cannot run becomes "stalled" on `/healthz` within five
minutes. Triage continues either way. `python -m relay.worker` takes `--directory` (reading only its `projects`)
and `--link-base`; without them the worker runs triage only, as before.

## Consequences

- A pass happens at least once per poll interval when idle, and once per triage job when busy.
- Two workers may run passes at once; each pass is one BEGIN IMMEDIATE transaction, steps fire at most once (D9),
  and outbox keys are unique. One of them waits for the other's lock.
- One heartbeat covers both duties. A worker that triages but cannot evaluate looks stalled; that is deliberate,
  because a missed escalation is a missed page, and Chapter 16 may split the signal.
- The worker's command does not take the webhook secret. Until Chapter 13 supplies it from the environment's secret
  store, passes run by the command write emails only.
- The pass runs before `claim`, so it uses none of a triage job's 60-second lease; a slow pass delays the next claim,
  not a job already held. A rule that cannot be timed is counted (`escalation_cannot_evaluate`) and the heartbeat is
  still written, because the evaluator itself works. The worker reaches the engine only through `relay.escalation`
  (new rule AR7).
- **This reverses part of ADR-014.** The pass needs `SELECT` on `tasks` and read-write access to the `esc_` tables;
  ADR-014's `infra/db/roles.sql` gives `relay_worker` no privilege on either ("no privilege at all on tasks"), and
  its restore test checks that. aisha.r accepted the change on 2026-12-10 because the pass reads tasks only to
  decide escalation and never updates one, so D3 and ESC-N01 still hold. The grant is not made here: `infra/` is
  outside this change, and Chapter 13 makes it with the rest of the deployment wiring.
- `EscalationStore` migrates its schema when opened (ADR-019). In the deployed environment the DDL must run once, as
  a separate migration role before the service and worker start, never as `relay_worker`; Chapter 13 wires that.
  Until then, local and lab runs migrate on open.
- **In the non-production environment no pass runs yet.** `infra/compute.tf` starts the worker without `--directory`
  and `--link-base`; Chapter 13 adds them with the grant. Steps fire today in local runs and the labs, where the
  worker is started with both flags.

## Rejected alternatives

### Option B — A second process type, `relay.escalator`, with its own loop
Rejected because: CON-1 and ADR-007 keep one worker type for one on-call rota; a second process doubles the deployment for a loop that takes milliseconds.
Revisit if: passes grow slow enough to delay triage, or need a schedule triage does not.

### Option C — The service runs a pass on each request
Rejected because: escalation would stop whenever traffic does, which is at night, when P1 rules matter most.
Revisit if: never for timed escalation.

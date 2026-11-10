# ADR-038 — Deployed detection, alert routing and paging, with automation limited to the kill switch

Status: accepted
Date: 2027-02-10
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N09, ESC-N04, D7, CON-1
Related: ADR-021, ADR-022, ADR-036, ADR-037
Revisit when: the paging provider changes; or automation is asked to do anything beyond tripping a kill switch.
Review by 2027-08-10 in any case.
Supersedes: none. Completes ADR-022's deployment.

## Context

Chapter 14 wrote agent-detection-v1 (DR-001 to DR-004) and evaluated it offline; delivering its alerts was left
to this chapter. The 2 February incident added a gap of its own: nothing watched sign-in failures, so a
credential-stuffing attack looked like a slow database. Relay's on-call policy pages the platform on-call,
escalates after 10 and 20 minutes, and sends security incidents to the security lead within an hour.

## Options considered

### Option A — One monitor beside a gateway collector evaluates SLOs, operational rules and both detection rule sets, and pages through a paging provider; automation may only trip a kill switch, behind its own switch

### Option B — Backend-native alarms for each rule, configured separately in the cloud provider

### Option C — Let automation also roll back, restart and fail over

## Decision

Option A.

- Sidecar collectors forward OTLP to a gateway collector; the monitor (`python -m relay.service.monitor`) runs
  once a minute over the gateway's files and the database. Each run evaluates the SLO burn rates, the
  operational rules AL-001 to AL-008 (metric values, a leak scan of its inputs, and from the database the
  worker's newest heartbeat and held P1 escalations) and both detection rule sets, whose alerts fall on
  five-minute evaluation boundaries with 28-day baselines. The trail's chain is verified first; a broken chain
  pages as TRAIL-TAMPER.
- New rule set relay-service-detection-v1 (SD-001 to SD-003): failure surges, many credentials from one network,
  and a success from a network with many failures.
- Routing (`infra/monitoring/routing.json`) follows the on-call policy. `relay.service.pager` sends events to the
  provider's HTTPS API with a deduplication key, IDs and evidence references, never telemetry values.
- Automation may trip an agent's kill switch for DR-001 and DR-003 only, at most three times an hour, and stops
  when `RELAY_AUTOMATION=off`; it then pages a person instead. Nothing automated restores anything. A router
  with no way to trip records `automation-unavailable` and pages; it never records a trip that did not happen.
- Grouping is the provider's: the pager client reuses an open page's deduplication key for repeats of its rule
  within an hour. Escalation after 10 and 20 minutes is configured in the provider's escalation policy.
- AL-006 pages when a P1 escalation held by the flood cap stays unacknowledged for 10 minutes (D7 review).

## Consequences

- One tested evaluator for every alert. Lab 16.1 and Lab 16.2 run the same code as the monitor.
- What runs in 4.27.0: the monitor command, tested end to end on files and a database. What does not yet: the
  task definitions (the sidecar, the gateway and monitor service, the telemetry log groups, the pager secret and
  the provider's host on the egress allowlist); the worker exporting its own telemetry, because the worker's
  entry point does not yet call `WorkerTelemetry` (AL-001 reads the heartbeat from the database instead); the
  weekly RF-001 job; and automated trips, because the agent registry's enabled flags and epochs still live in
  each process's memory (ADR-020), so the monitor has nothing to trip. Until those land, DR-001 and DR-003 page
  the security on-call, who trips the switch by the runbook. Like the rest of the environment, the deployment
  carries no traffic until the PostgreSQL adapter lands (ADR-031).
- If the monitor stops, nothing inside Relay notices. The provider's heartbeat check, fed by each successful
  run, is the dead man's switch; owner sam.o, to be configured by 2027-03-31.
- Sidecar-to-gateway OTLP is plain HTTP inside the VPC with no authentication, so anything in Relay's task
  security group could forge security events or metrics, and raise or hide alerts. The security group limits
  who can send; mutual TLS or a shared token on the gateway's receivers is the next step (owner aisha.r, by
  2027-04-30).

## Rejected alternatives

### Option B — Backend-native alarms for each rule, configured separately in the cloud provider
Rejected because: each rule would be written twice, once as tested code and once as alarm configuration, and the two would drift; the multi-window rows and the detection baselines are awkward to express there.
Revisit if: Relay moves to a managed observability backend that evaluates SLO burn rates natively and can be tested against Lab 16.1's data.

### Option C — Let automation also roll back, restart and fail over
Rejected because: the 2 February rollback was the wrong action taken quickly; an automated version would have taken it faster, and a wrong rollback during an attack costs time the defenders need.
Revisit if: a remediation is shown, by game days, to be safe whenever its alert fires; then automate that one, with its own switch.

# Runbook — database latency

Owner: sam.o. Alerts: SLO-API-LATENCY and SLO-API-AVAIL burn rates; often AL-001 too.

1. Confirm the database is the slow part: the share of request time in `db` client spans, by
   `db.operation.name` and `db.collection.name`, against the hour before.
2. Ask what changed: deploys in the window (the 15:00 train), migrations, configuration changes. A change is a
   cause only if its component shows in the slow spans; a deploy that touched no database code is not a cause
   because it came first.
3. Ask who is calling: request rate by route, and the security view. A surge on one route (sign-in, export)
   points at load, possibly hostile; follow `credential-stuffing.md` if SD-001 to SD-003 fire.
4. Mitigate through the remediation gate: shed the load that causes it, fail over the database (two people),
   or roll back a change whose spans show it is the cause (two people).
5. After mitigation, watch the burn rate fall below every threshold before closing.

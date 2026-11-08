# Restore test record — Relay database

| Field | Value |
| --- | --- |
| Source instance and restore point (UTC) | |
| Restored instance (with `expires` tag) | |
| Requested at / usable at (UTC), minutes | |
| Row counts: tasks, triage_jobs, worker_heartbeats (source / restored) | |
| Grants match `infra/db/roles.sql` | (yes / no, with differences) |
| `relay_worker` cannot read `tasks` (tested) | |
| Restored instance deleted at (UTC) | |
| Tester / reviewer | |

Failover test (optional, separate run): time from `reboot --force-failover` to the first successful
query from the service and the worker; triage jobs lost or duplicated (expected 0 lost; duplicates
are tolerated by idempotency keys and leases).

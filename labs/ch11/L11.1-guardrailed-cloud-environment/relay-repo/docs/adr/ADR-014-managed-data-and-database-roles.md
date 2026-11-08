# ADR-014 — Managed PostgreSQL with a standby, separate database roles, one key, and a shared rate limiter

Status: accepted
Date: 2026-11-30
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ADR-007, D3, ESC-N01, ESC-N03, ESC-N04, CON-1, CON-3
Revisit when: the database becomes the limit on the service's throughput (Chapter 17's load tests); or a restore test misses its target; or Relay runs in a second region. Review by 2027-11-30 in any case.
Supersedes: none.

## Context

ADR-007 accepted one database as a single point of failure, one database role shared by the service and the
worker, and a rate limiter counted in each process's memory. Each was a consequence to fix before deployment.
The 4.19.0 snapshot stores everything in SQLite.

## Options considered

### Option A — Amazon RDS for PostgreSQL, Multi-AZ, IAM authentication for two application roles, a customer-managed key, and the rate limit in a database table

### Option B — Amazon Aurora PostgreSQL with a reader, and the rate limit in a managed cache

### Option C — PostgreSQL on a self-managed instance, with a cron backup to object storage

## Decision

Option A. One RDS PostgreSQL instance, `db.t4g.small`, with a synchronous standby in the second zone, storage
encrypted with Relay's customer-managed key, deletion protection, 7 days of automated backups, a final snapshot
on delete, and TLS required. The master password is generated and rotated by RDS in Secrets Manager. The service
and the worker log in as `relay_service` and `relay_worker` with IAM tokens, never passwords, under the grants in
`infra/db/roles.sql`: the worker has no privilege on `tasks`, so a suggestion cannot become a task's priority
even through a compromised worker (D3, ESC-N01).

The rate limit moves to a table, `rate_limit_windows`, through `relay.service.sharedlimit.SharedRateLimiter`, with
the same window rule and interface as 4.19.0's limiter. Two processes now share one count of 600 per minute,
which `tests/test_service_sharedlimit.py` checks with two real processes.

At the price table's assumptions the database is 23.1% of the environment's fixed cost, with the standby doubling
both instance and storage.

## Consequences

- Multi-AZ protects against the loss of an instance or a zone. Failover is automatic and takes on the order of a
  minute or two, during which connections fail; the worker's leases and retries (ADR-007) must absorb it, and the
  failover test in `infra/runbooks/restore-test.md` measures whether they do. It does not protect against a bad
  write or a dropped table: backups and point-in-time restore do, and a monthly restore test proves them.
- One region. A regional outage takes Relay's non-production environment down; production's answer is a later
  decision.
- 4.21.0 still stores data in SQLite. The PostgreSQL store adapter is a dependency (a driver), so it needs its
  own ADR under Lab 6.2's FF005 and Chapter 13's review. Until it lands, this environment is planned and checked
  but carries no traffic: Lab 11.1's live mode starts the services with no tasks, and the shared limiter's SQL is
  tested on SQLite only.
- Secrets in state: none. This configuration creates the directory secret's container, not its value.
- A cache (Option B) stays available for later; the rate limit is one small write per request, which a
  `db.t4g.small` can absorb at non-production volume. Chapter 17 measures it under load.

## Rejected alternatives

### Option B — Amazon Aurora PostgreSQL with a reader, and the rate limit in a managed cache
Rejected because: it adds a second managed service and a second network path for one counter, and costs more at this size, for read scaling that non-production does not need.
Revisit if: Chapter 17's load tests show the database is the bottleneck, or the rate limit's writes contend with the queue's.

### Option C — PostgreSQL on a self-managed instance, with a cron backup to object storage
Rejected because: patching, failover and backup verification would fall on one rota of eight engineers, which is the operational load CON-1 rules out.
Revisit if: a feature needs a PostgreSQL extension that the managed service does not offer.

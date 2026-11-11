# ADR-031 — Deployment wiring: shared stores in the WSGI app, a worker that runs escalation passes, and a separate migration role

Status: accepted
Date: 2027-01-21
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: D3, ESC-N01, ESC-N03, ESC-N09, CON-1
Related: ADR-014, ADR-015, ADR-017, ADR-018, ADR-019, ADR-030
Revisit when: the PostgreSQL store adapter lands (its own ADR); or a process type is added. Review by 2027-07-21
in any case.
Supersedes: none. Implements the grant ADR-017 accepted on 2026-12-10.

## Context

4.21.0 added `relay.service.wsgi` and `SharedRateLimiter` but left the deployment loose, and 4.22.0 left the
worker's cloud grant and flags to later. Reading the configuration against the code found five gaps:

1. `wsgi.create_app` built the escalation routes on an in-memory store, so a rule saved through one gunicorn
   process was invisible to the other and lost on restart.
2. The routes' links used a default workspace address rather than the configured one.
3. The service task set `RELAY_DIRECTORY_FILE`, but nothing wrote that file, and the root filesystem is
   read-only. The directory secret sat in the main container's environment.
4. The worker's task ran `python -m relay.worker` with no `--db`, `--directory` or `--link-base`, so no
   escalation pass would run, and `relay_worker` had no grant on `tasks` or the `esc_` tables.
5. The stores create and migrate their own tables, so the application roles would need DDL rights.

## Options considered

### Option A — Wire each setting explicitly, write the directory from an init container, run migrations as a one-off task under its own role, and refuse to start without a shared database

### Option B — Give both application roles DDL rights and let each process migrate at start-up

## Decision

Option A.

- `create_app` passes the shared `EscalationStore` and `RELAY_LINK_BASE` (required, `https://` only).
- An init container receives the directory secret, writes it to a task-local volume and exits; the main
  container mounts the volume read-only and starts only after the init container succeeds.
- The worker's entry point passes `--db`, `--directory` and `--link-base`. `infra/db/roles.sql` grants
  `relay_worker` `SELECT` on `tasks` and exactly the `esc_` privileges the pass uses, with no `DELETE` and no
  access to `esc_audit`. The service gets the `esc_` privileges its routes use.
- `relay_migrator` is the only role with `CREATE` on the schema. `python -m relay.service.migrate` runs as a
  one-off task before the service and worker are updated, and the deployment stops if it exits non-zero.
- The database path is a placeholder until the PostgreSQL adapter exists: each task gets a writable,
  task-local volume at `/var/lib/relay`, so the SQLite file can be opened, but no two tasks share it. So `wsgi`
  and `migrate` refuse to start when `RELAY_DB_HOST` is set, and the desired counts stay at zero.

## Consequences

- The configuration supplies every setting the code requires, and `tests/test_infra_deploy_wiring.py` checks
  that, including that each database path is on a writable mount. The database itself is a placeholder, and
  the environment carries no traffic until the adapter lands; that is a dependency ADR and a review under
  ADR-028.
- The worker command itself has no such check; the zero desired count keeps it from running alone.
- The webhook secret is not yet supplied to the worker; webhook delivery belongs with the delivery adapters, and
  until then the worker writes no webhook events.
- Migrations now have one owner and one moment, which also makes ADR-019's downgrade rule enforceable.

## Rejected alternatives

### Option B — Give both application roles DDL rights and let each process migrate at start-up
Rejected because: a compromised service or worker could then drop or rebuild tables, including `esc_audit`, which SEC-09 protects, and two processes starting together would race to migrate.
Revisit if: never for production; tests and local runs keep the self-migrating stores.

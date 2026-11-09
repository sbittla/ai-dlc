-- Separate database roles for Relay's process types (ADR-014; worker grants ADR-017; migration role ADR-031).
--
-- Applied once per environment by the platform team, as the RDS-managed master
-- user, before the first deployment. Every role logs in with short-lived IAM
-- authentication tokens (the rds_iam role), never with a password.
--
-- ADR-007 recorded that the service and the worker shared one database role, so a
-- compromised worker could reach every table. ADR-014 split them. ADR-017 then gave
-- the worker read access to tasks, because the escalation pass reads each task's
-- project and status; it still cannot insert, change or delete a task, so a triage
-- suggestion cannot become a task's priority even if the worker is taken over
-- (D3, ESC-N01). Neither application role can change the schema: from 4.25.0 the
-- tables are created and migrated by relay_migrator, in a one-off task that runs
-- before the service and worker start (infra/runbooks/deploy.md), and it owns them.
-- No role may delete from esc_audit (SEC-09); only a migration rebuilds it.
--
-- tests/test_infra_db_roles.py checks these rules on every change.

CREATE ROLE relay_service LOGIN;
CREATE ROLE relay_worker LOGIN;
CREATE ROLE relay_migrator LOGIN;
GRANT rds_iam TO relay_service;
GRANT rds_iam TO relay_worker;
GRANT rds_iam TO relay_migrator;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO relay_service;
GRANT USAGE ON SCHEMA public TO relay_worker;
GRANT USAGE, CREATE ON SCHEMA public TO relay_migrator;

-- From here on, each grant names a table that relay_migrator creates. The deployment
-- applies this section again after the first migration (infra/runbooks/deploy.md).

-- The service: reads tasks, queues and reads triage jobs, reads worker heartbeats
-- for /healthz, and keeps the shared rate-limit windows.
GRANT SELECT ON tasks TO relay_service;
GRANT SELECT, INSERT ON triage_jobs TO relay_service;
GRANT USAGE ON SEQUENCE triage_jobs_id_seq TO relay_service;
GRANT SELECT ON worker_heartbeats TO relay_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_windows TO relay_service;

-- The service's escalation routes (ADR-009, ADR-016): save, replace and delete rules
-- (a deletion sets deleted_at), audit every change, write rule notices to the outbox,
-- and set a task's priority or acknowledgement.
GRANT SELECT ON esc_schema TO relay_service;
GRANT SELECT, INSERT, UPDATE ON esc_rules TO relay_service;
GRANT SELECT, INSERT ON esc_audit TO relay_service;
GRANT SELECT, INSERT, UPDATE ON esc_state TO relay_service;
GRANT SELECT, INSERT ON esc_activity TO relay_service;
GRANT SELECT, INSERT ON esc_outbox TO relay_service;

-- The worker: claims, completes and fails triage jobs, and records its heartbeat.
GRANT SELECT, UPDATE ON triage_jobs TO relay_worker;
GRANT SELECT, INSERT, UPDATE ON worker_heartbeats TO relay_worker;

-- The worker's escalation pass (ADR-017, accepted by aisha.r on 2026-12-10): reads
-- tasks and rules, and records state, fired steps, activity, held steps and messages.
GRANT SELECT ON tasks TO relay_worker;
GRANT SELECT ON esc_schema TO relay_worker;
GRANT SELECT ON esc_rules TO relay_worker;
GRANT SELECT, INSERT, UPDATE ON esc_state TO relay_worker;
GRANT SELECT, INSERT ON esc_fired TO relay_worker;
GRANT SELECT, INSERT ON esc_activity TO relay_worker;
GRANT SELECT, INSERT ON esc_outbox TO relay_worker;
GRANT SELECT, INSERT, UPDATE ON esc_held TO relay_worker;

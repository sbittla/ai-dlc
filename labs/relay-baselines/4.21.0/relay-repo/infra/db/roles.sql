-- Separate database roles for Relay's two process types (ADR-014).
--
-- Applied once per environment by the platform team, as the RDS-managed master
-- user, after the schema exists. Both application roles log in with short-lived
-- IAM authentication tokens (the rds_iam role), never with a password.
--
-- ADR-007 recorded that the service and the worker shared one database role, so a
-- compromised worker could reach every table. These grants close that: the worker
-- has no privilege at all on tasks, so a triage suggestion cannot change a task even
-- if the worker process is taken over (D3, ESC-N01).
--
-- tests/test_infra_db_roles.py checks these rules on every change.

CREATE ROLE relay_service LOGIN;
CREATE ROLE relay_worker LOGIN;
GRANT rds_iam TO relay_service;
GRANT rds_iam TO relay_worker;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO relay_service;
GRANT USAGE ON SCHEMA public TO relay_worker;

-- The service: reads tasks, queues and reads triage jobs, reads worker heartbeats
-- for /healthz, and keeps the shared rate-limit windows.
GRANT SELECT ON tasks TO relay_service;
GRANT SELECT, INSERT ON triage_jobs TO relay_service;
GRANT USAGE ON SEQUENCE triage_jobs_id_seq TO relay_service;
GRANT SELECT ON worker_heartbeats TO relay_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_windows TO relay_service;

-- The worker: claims, completes and fails triage jobs, and records its heartbeat.
GRANT SELECT, UPDATE ON triage_jobs TO relay_worker;
GRANT SELECT, INSERT, UPDATE ON worker_heartbeats TO relay_worker;

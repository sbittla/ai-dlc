# Runbook — restore test for Relay's database

Owner: sam.o. Monthly in non-production, and before any production cut-over (ADR-014).
A backup that has never been restored is an assumption, not a control.

1. **Pick a restore point** within the 7-day backup window, and note the time.
2. **Restore to a new instance** (`aws rds restore-db-instance-to-point-in-time`), with the same
   subnet group, security group, parameter group, KMS key and tags, plus `expires` set to
   tomorrow. Never restore over the running instance.
3. **Check the data.** Row counts of `tasks`, `triage_jobs` and `worker_heartbeats` against the
   source at the restore point; the grants in `infra/db/roles.sql` are present; an IAM-token login
   as `relay_worker` cannot `SELECT` from `tasks`.
4. **Time it.** Record minutes from request to a usable database. That number is the restore
   part of the recovery time objective, measured rather than assumed.
5. **Delete the restored instance** and confirm with the tagged-resource list.
6. **Record it** with the template in Lab 11.1 (`templates/restore-test-record.md`).

Failover is a different test: `aws rds reboot-db-instance --force-failover` on the Multi-AZ
instance, while the service and worker run, recording how long connections fail and whether any
triage job is lost or duplicated.

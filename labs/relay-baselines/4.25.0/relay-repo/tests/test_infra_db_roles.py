"""Database role fitness checks (4.21.0, ADR-014; worker grants ADR-017 and migration role ADR-031 in 4.25.0),
read from infra/db/roles.sql.

They check the grants as written. Whether the live database matches them is a
runtime question; the restore test (infra/runbooks/restore-test.md) compares them.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "infra" / "db" / "roles.sql").read_text(encoding="utf-8")
GRANT = re.compile(r"^GRANT\s+([A-Z, ]+?)\s+ON\s+(?:SEQUENCE\s+)?(\w+)\s+TO\s+(\w+);", re.M)
APP_ROLES = {"relay_service", "relay_worker"}
ESC_TABLES = {"esc_schema", "esc_rules", "esc_audit", "esc_state", "esc_fired", "esc_activity", "esc_outbox",
              "esc_held"}


def grants() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for privs, obj, role in GRANT.findall(SQL):
        if obj == "SCHEMA":
            continue
        out.setdefault((role, obj), set()).update(p.strip() for p in privs.split(","))
    return out


def test_three_login_roles_all_using_iam_tokens():
    assert re.findall(r"^CREATE ROLE (\w+) LOGIN;", SQL, re.M) == ["relay_service", "relay_worker", "relay_migrator"]
    assert re.findall(r"^GRANT rds_iam TO (\w+);", SQL, re.M) == ["relay_service", "relay_worker", "relay_migrator"]
    assert "PASSWORD" not in SQL.upper().replace("NEVER WITH A PASSWORD", "")


def test_the_worker_reads_tasks_and_never_writes_them():
    assert grants()[("relay_worker", "tasks")] == {"SELECT"}


def test_nobody_writes_or_deletes_tasks():
    on_tasks = {role: privs for (role, obj), privs in grants().items() if obj == "tasks"}
    assert on_tasks == {"relay_service": {"SELECT"}, "relay_worker": {"SELECT"}}


def test_the_service_cannot_change_a_job_after_queueing_it():
    assert grants()[("relay_service", "triage_jobs")] == {"SELECT", "INSERT"}


def test_the_worker_reads_and_writes_every_table_the_escalation_pass_uses():
    worker = {obj: privs for (role, obj), privs in grants().items() if role == "relay_worker" and obj in ESC_TABLES}
    assert worker == {"esc_schema": {"SELECT"}, "esc_rules": {"SELECT"},
                      "esc_state": {"SELECT", "INSERT", "UPDATE"}, "esc_fired": {"SELECT", "INSERT"},
                      "esc_activity": {"SELECT", "INSERT"}, "esc_outbox": {"SELECT", "INSERT"},
                      "esc_held": {"SELECT", "INSERT", "UPDATE"}}


def test_the_worker_cannot_change_rules_or_the_audit_log():
    assert grants()[("relay_worker", "esc_rules")] == {"SELECT"}
    assert ("relay_worker", "esc_audit") not in grants()


def test_nobody_updates_or_deletes_the_escalation_audit_log():
    assert all(privs <= {"SELECT", "INSERT"} for (role, obj), privs in grants().items() if obj == "esc_audit")


def test_no_application_role_can_delete_escalation_rows():
    assert not any("DELETE" in privs for (role, obj), privs in grants().items() if obj in ESC_TABLES)


def test_only_the_migration_role_can_change_the_schema():
    assert re.findall(r"^GRANT USAGE, CREATE ON SCHEMA public TO (\w+);", SQL, re.M) == ["relay_migrator"]
    assert not re.search(r"\b(ALL PRIVILEGES|TRUNCATE|SUPERUSER|CREATEROLE|CREATEDB)\b", SQL)
    grants_with_create = [ln for ln in SQL.splitlines() if ln.startswith("GRANT") and "CREATE" in ln]
    assert grants_with_create == ["GRANT USAGE, CREATE ON SCHEMA public TO relay_migrator;"]


def test_every_table_grant_is_to_an_application_role():
    assert {role for role, _ in grants()} == APP_ROLES


def test_the_restore_runbook_checks_the_worker_grant_as_written():
    runbook = (ROOT / "infra" / "runbooks" / "restore-test.md").read_text(encoding="utf-8")
    assert "cannot `INSERT`, `UPDATE` or `DELETE` on `tasks`" in runbook
    assert "relay_migrator" in runbook

"""Database role fitness checks (4.21.0, ADR-014), read from infra/db/roles.sql.

They check the grants as written. Whether the live database matches them is a
runtime question; the restore test (infra/runbooks/restore-test.md) compares them.
"""

import re
from pathlib import Path

SQL = (Path(__file__).resolve().parent.parent / "infra" / "db" / "roles.sql").read_text(encoding="utf-8")
GRANT = re.compile(r"^GRANT\s+([A-Z, ]+?)\s+ON\s+(?:SEQUENCE\s+)?(\w+)\s+TO\s+(\w+);", re.M)


def grants() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for privs, obj, role in GRANT.findall(SQL):
        if obj == "SCHEMA":
            continue
        out.setdefault((role, obj), set()).update(p.strip() for p in privs.split(","))
    return out


def test_two_login_roles_both_using_iam_tokens():
    assert re.findall(r"^CREATE ROLE (\w+) LOGIN;", SQL, re.M) == ["relay_service", "relay_worker"]
    assert re.findall(r"^GRANT rds_iam TO (\w+);", SQL, re.M) == ["relay_service", "relay_worker"]
    assert "PASSWORD" not in SQL.upper().replace("NEVER WITH A PASSWORD", "")


def test_the_worker_has_no_privilege_on_tasks():
    assert ("relay_worker", "tasks") not in grants()


def test_nobody_writes_or_deletes_tasks():
    assert grants()[("relay_service", "tasks")] == {"SELECT"}


def test_the_service_cannot_change_a_job_after_queueing_it():
    assert grants()[("relay_service", "triage_jobs")] == {"SELECT", "INSERT"}


def test_no_role_can_change_the_schema_or_own_objects():
    assert not re.search(r"\b(ALL PRIVILEGES|CREATE ON|TRUNCATE|SUPERUSER|CREATEROLE|CREATEDB)\b", SQL)


def test_every_grant_is_to_an_application_role():
    assert {role for role, _ in grants()} == {"relay_service", "relay_worker"}

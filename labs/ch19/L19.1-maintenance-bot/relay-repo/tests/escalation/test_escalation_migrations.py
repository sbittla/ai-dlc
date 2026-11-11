"""Schema version 2 and its migration (spec ESC-SPEC-1 1.2.0, SEC-09; ADR-019). Task T21.

Spec: ESC-SPEC-1
Spec version: 1.2.0

The oracle for every migration test is the database as it was before: the
rows are written out by hand below and compared with what the migration leaves.
"""

import sqlite3

import pytest

from relay.escalation import EscalationStore, MigrationRefused, migrations
from relay.escalation.store import SCHEMA

# Three audit rows as a 4.20.0 database holds them: a save, a refusal with problems, and a save with NULLs.
V1_AUDIT = [
    (1, "2026-11-24T01:30:00.000000Z", 2, "R-ROT-P1", "saved", None, None, '{"priority": "P1"}', None),
    (2, "2026-11-24T01:31:00.000000Z", 4, "R-ROT-P1", "refused", "invalid_document", None, None,
     '["$.steps[0].targets[0]"]'),
    (3, "2026-11-24T01:32:00.000000Z", 2, "R-ROT-P2", "saved", None, '{"priority": "P2"}', '{"priority": "P2"}', None),
]
V1_RULE = ("R-ROT-P1", 10, "P1", '{"priority": "P1", "project_id": 10, "rule_id": "R-ROT-P1"}',
           "2026-11-24T01:30:00.000000Z")


def v1_database() -> sqlite3.Connection:
    """A database exactly as Relay 4.20.0 and 4.21.0 left it: SCHEMA only, no esc_schema table."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO esc_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", V1_AUDIT)
    conn.execute("INSERT INTO esc_rules VALUES (?, ?, ?, ?, ?)", V1_RULE)
    return conn


def audit_rows(conn):
    return conn.execute(f"SELECT {migrations.AUDIT_COLUMNS} FROM esc_audit ORDER BY id").fetchall()


def test_a_4_21_0_database_is_version_1_and_a_new_store_is_version_2():
    assert migrations.schema_version(v1_database()) == 1
    assert migrations.schema_version(EscalationStore().conn) == 2


def test_SEC09_migrating_keeps_every_audit_row_and_rule_exactly():
    conn = v1_database()
    assert migrations.migrate(conn) == [2]
    assert audit_rows(conn) == V1_AUDIT
    assert conn.execute("SELECT rule_id, project_id, priority, document, updated_at, deleted_at FROM esc_rules"
                        ).fetchall() == [V1_RULE + (None,)]
    assert migrations.migrate(conn) == []  # a second run changes nothing


def test_version_2_accepts_a_deleted_outcome_and_version_1_did_not():
    conn = v1_database()
    deleted = (4, "2026-12-14T10:00:00.000000Z", 2, "R-ROT-P1", "deleted", None, '{}', None, None)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO esc_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", deleted)
    migrations.migrate(conn)
    conn.execute("INSERT INTO esc_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", deleted)
    assert len(audit_rows(conn)) == 4


def test_SEC09_a_copy_that_forgets_a_column_is_refused_and_nothing_changes(monkeypatch):
    conn = v1_database()
    # The commonest real migration bug: one column left out of the copy. Row 2's problems would become NULL.
    monkeypatch.setattr(migrations, "AUDIT_COLUMNS", "id, at, actor_id, rule_id, outcome, code, before, after")
    with pytest.raises(MigrationRefused):
        migrations.migrate(conn)
    monkeypatch.undo()
    assert migrations.schema_version(conn) == 1
    assert audit_rows(conn) == V1_AUDIT
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "esc_audit_v2" not in tables and "esc_schema" not in tables


def test_SEC09_a_downgrade_without_deletions_restores_version_1_with_every_row():
    conn = v1_database()
    migrations.migrate(conn)
    assert migrations.downgrade(conn, 1) == [2]
    assert migrations.schema_version(conn) == 1
    assert audit_rows(conn) == V1_AUDIT
    columns = [r[1] for r in conn.execute("PRAGMA table_info(esc_rules)")]
    assert columns == ["rule_id", "project_id", "priority", "document", "updated_at"]


def test_SEC09_a_downgrade_that_would_lose_a_deletion_is_refused_and_nothing_changes():
    conn = v1_database()
    migrations.migrate(conn)
    conn.execute("UPDATE esc_rules SET deleted_at = '2026-12-14T10:00:00.000000Z'")
    with pytest.raises(MigrationRefused):
        migrations.downgrade(conn, 1)
    assert migrations.schema_version(conn) == 2
    assert conn.execute("SELECT deleted_at FROM esc_rules").fetchone() == ("2026-12-14T10:00:00.000000Z",)


def test_two_stores_opening_one_file_migrate_it_once(tmp_path):
    path = str(tmp_path / "relay.db")
    first, second = EscalationStore(path), EscalationStore(path)
    assert migrations.schema_version(second.conn) == 2
    assert first.conn.execute("SELECT version FROM esc_schema").fetchall() == [(2,)]
    first.conn.close()
    second.conn.close()

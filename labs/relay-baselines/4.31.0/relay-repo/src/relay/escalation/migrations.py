"""Schema versions of the escalation engine's tables, and the migrations between them (ADR-019).

Version 1 is the 4.20.0 schema (`store.SCHEMA`). Version 2 (4.22.0, spec 1.2.0)
lets a rule be deleted: `esc_rules` gains `deleted_at`, and `esc_audit`'s
outcome may be 'deleted'. SQLite cannot change a CHECK constraint in place, so
version 2 rebuilds `esc_audit`: create the new table, copy every row, prove the
copy is exact, and only then drop the old table. All of it is one transaction,
so a failed proof leaves version 1 untouched.

    migrate(conn)              # to the latest version; a no-op if already there
    downgrade(conn, 1)         # back to 4.20.0's schema, refused if that would lose data

The version lives in `esc_schema`, which this module owns. Two processes that
open the same database at once are safe: each takes the write lock with BEGIN
IMMEDIATE and reads the version again inside the transaction.
"""

from __future__ import annotations

import sqlite3

LATEST = 2

AUDIT_COLUMNS = "id, at, actor_id, rule_id, outcome, code, before, after, problems"
RULE_COLUMNS_V1 = "rule_id, project_id, priority, document, updated_at"

_AUDIT_TABLE = """
CREATE TABLE {name} (
    id       INTEGER PRIMARY KEY,
    at       TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    rule_id  TEXT NOT NULL,
    outcome  TEXT NOT NULL CHECK (outcome IN ({outcomes})),
    code     TEXT,
    before   TEXT,
    after    TEXT,
    problems TEXT
)"""
_RULES_TABLE_V1 = """
CREATE TABLE {name} (
    rule_id    TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    priority   TEXT NOT NULL,
    document   TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""


class MigrationRefused(RuntimeError):
    """A migration would lose data, or its copy did not match; nothing was changed."""


def schema_version(conn: sqlite3.Connection) -> int:
    """The schema's version: 0 for a database without escalation tables, 1 for 4.20.0's, else as recorded."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "esc_schema" in tables:
        row = conn.execute("SELECT MAX(version) FROM esc_schema").fetchone()
        if row[0] is not None:
            return row[0]
    return 1 if "esc_rules" in tables else 0


def migrate(conn: sqlite3.Connection, target: int = LATEST) -> list[int]:
    """Upgrade to `target`. Returns the versions applied, in order (empty if none were needed)."""
    if not 1 <= target <= LATEST:
        raise ValueError(f"target must be from 1 to {LATEST}")
    applied: list[int] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = schema_version(conn)  # read again under the write lock
        if current == 0:
            raise MigrationRefused("no escalation tables: create them with store.SCHEMA first")
        conn.execute("CREATE TABLE IF NOT EXISTS esc_schema (version INTEGER NOT NULL)")
        for version in range(current + 1, target + 1):
            _UP[version](conn)
            conn.execute("INSERT INTO esc_schema (version) VALUES (?)", (version,))
            applied.append(version)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return applied


def downgrade(conn: sqlite3.Connection, target: int) -> list[int]:
    """Return to `target`'s schema. Refused, with nothing changed, if any row would be lost."""
    applied: list[int] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = schema_version(conn)
        if not 1 <= target <= current:
            raise ValueError(f"cannot downgrade from {current} to {target}")
        for version in range(current, target, -1):
            _DOWN[version](conn)
            conn.execute("DELETE FROM esc_schema WHERE version = ?", (version,))
            applied.append(version)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return applied


def copy_exactly(conn: sqlite3.Connection, source: str, target: str, columns: str) -> int:
    """Copy every row of `source` into `target` and prove the copy: same count, and no row in one but not the other.

    The proof compares every column of `target`, read from the database, not
    the `columns` the copy used: a column left out of the copy is then a
    difference, not a shared mistake. Returns the number of rows copied. Raises
    MigrationRefused if the proof fails; the caller's transaction is then
    rolled back, and the source is untouched.
    """
    conn.execute(f"INSERT INTO {target} ({columns}) SELECT {columns} FROM {source}")
    every = ", ".join(r[1] for r in conn.execute(f"PRAGMA table_info({target})"))
    before = conn.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0]
    after = conn.execute(f"SELECT COUNT(*) FROM {target}").fetchone()[0]
    missing = conn.execute(f"SELECT COUNT(*) FROM (SELECT {every} FROM {source} "
                           f"EXCEPT SELECT {every} FROM {target})").fetchone()[0]
    extra = conn.execute(f"SELECT COUNT(*) FROM (SELECT {every} FROM {target} "
                         f"EXCEPT SELECT {every} FROM {source})").fetchone()[0]
    if (before, missing, extra) != (after, 0, 0):
        raise MigrationRefused(f"copy of {source} is not exact: {before} rows before, {after} after, "
                               f"{missing} missing, {extra} unexpected")
    return after


def _up_2(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE esc_rules ADD COLUMN deleted_at TEXT")
    conn.execute(_AUDIT_TABLE.format(name="esc_audit_v2", outcomes="'saved', 'refused', 'deleted'"))
    copy_exactly(conn, "esc_audit", "esc_audit_v2", AUDIT_COLUMNS)
    conn.execute("DROP TABLE esc_audit")
    conn.execute("ALTER TABLE esc_audit_v2 RENAME TO esc_audit")


def _down_2(conn: sqlite3.Connection) -> None:
    deleted_rules = conn.execute("SELECT COUNT(*) FROM esc_rules WHERE deleted_at IS NOT NULL").fetchone()[0]
    deletions = conn.execute("SELECT COUNT(*) FROM esc_audit WHERE outcome = 'deleted'").fetchone()[0]
    if deleted_rules or deletions:
        raise MigrationRefused(f"version 1 cannot hold {deleted_rules} deleted rule(s) and {deletions} deletion "
                               "audit entr(ies); restore from a backup instead")
    conn.execute(_AUDIT_TABLE.format(name="esc_audit_v1", outcomes="'saved', 'refused'"))
    copy_exactly(conn, "esc_audit", "esc_audit_v1", AUDIT_COLUMNS)
    conn.execute("DROP TABLE esc_audit")
    conn.execute("ALTER TABLE esc_audit_v1 RENAME TO esc_audit")
    conn.execute(_RULES_TABLE_V1.format(name="esc_rules_v1"))
    copy_exactly(conn, "esc_rules", "esc_rules_v1", RULE_COLUMNS_V1)
    conn.execute("DROP TABLE esc_rules")
    conn.execute("ALTER TABLE esc_rules_v1 RENAME TO esc_rules")


_UP = {2: _up_2}
_DOWN = {2: _down_2}

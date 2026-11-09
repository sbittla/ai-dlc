"""The escalation engine's tables (ADR-011). Only relay.escalation reads or writes them.

All tables are prefixed `esc_` and live in Relay's one database (ADR-007):

    esc_rules      the saved rules, as contract documents; a deleted rule keeps its row, with deleted_at set
    esc_audit      every rule change, deletion and refused change (ESC-N03; 400-day retention is Chapter 11's)
    esc_state      per task: the priority a person set, the model's suggestion, the acknowledgement
    esc_fired      (task, rule, step) once fired; the primary key is D9's "never twice"
    esc_activity   what the task's activity shows about escalation
    esc_outbox     emails and webhook events for the delivery adapters; nothing is sent from here
    esc_held       escalation emails held by the flood cap, until the hour's summary

Times are stored as UTC text with microseconds, so text order is time order.

`SCHEMA` is version 1 (4.20.0). Opening a store migrates it to the latest
version (`migrations.py`, ADR-019); version 2 adds rule deletion (spec 1.2.0).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from . import migrations
from .model import EscalationState, Rule

UTC = timezone.utc
_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

SCHEMA = """
CREATE TABLE IF NOT EXISTS esc_rules (
    rule_id    TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    priority   TEXT NOT NULL,
    document   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS esc_audit (
    id       INTEGER PRIMARY KEY,
    at       TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    rule_id  TEXT NOT NULL,
    outcome  TEXT NOT NULL CHECK (outcome IN ('saved', 'refused')),
    code     TEXT,
    before   TEXT,
    after    TEXT,
    problems TEXT
);
CREATE TABLE IF NOT EXISTS esc_state (
    task_id              INTEGER PRIMARY KEY,
    project_id           INTEGER NOT NULL,
    priority             TEXT,
    priority_set_at      TEXT,
    priority_set_by      INTEGER,
    suggested_priority   TEXT,
    suggested_confidence INTEGER,
    acknowledged_at      TEXT,
    acknowledged_by      INTEGER
);
CREATE TABLE IF NOT EXISTS esc_fired (
    task_id  INTEGER NOT NULL,
    rule_id  TEXT NOT NULL,
    step     INTEGER NOT NULL,
    fired_at TEXT NOT NULL,
    PRIMARY KEY (task_id, rule_id, step)
);
CREATE TABLE IF NOT EXISTS esc_activity (
    id      INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    detail  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS esc_outbox (
    id         INTEGER PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    channel    TEXT NOT NULL CHECK (channel IN ('email', 'webhook')),
    kind       TEXT NOT NULL,
    recipient  TEXT NOT NULL,
    headers    TEXT NOT NULL,
    body       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS esc_held (
    id             INTEGER PRIMARY KEY,
    target_id      INTEGER NOT NULL,
    task_id        INTEGER NOT NULL,
    rule_id        TEXT NOT NULL,
    step           INTEGER NOT NULL,
    held_at        TEXT NOT NULL,
    summary_due_at TEXT NOT NULL,
    summarized     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (target_id, task_id, rule_id, step)
);
"""


def ts(instant: datetime) -> str:
    if instant.utcoffset() is None:
        raise ValueError("times must be aware")
    return instant.astimezone(UTC).strftime(_FORMAT)


def dt(text: str | None) -> datetime | None:
    return None if text is None else datetime.strptime(text, _FORMAT).replace(tzinfo=UTC)


@dataclass(frozen=True)
class OutboxItem:
    id: int
    created_at: datetime
    channel: str  # email | webhook
    kind: str  # escalation | summary | task.escalated
    recipient: str  # a user ID for email (resolved by the adapter); the endpoint URL for webhooks
    headers: dict
    body: str  # an EmailMessage document as JSON, or the webhook body exactly as signed


@dataclass(frozen=True)
class AuditEntry:
    id: int
    at: datetime
    actor_id: int
    rule_id: str
    outcome: str
    code: str | None
    before: dict | None
    after: dict | None
    problems: list | None


class EscalationStore:
    """The engine's persistence. Pass a path, or an open sqlite3 connection shared with other modules."""

    def __init__(self, db: str | sqlite3.Connection = ":memory:") -> None:
        self.conn = db if isinstance(db, sqlite3.Connection) else sqlite3.connect(db, isolation_level=None)
        self.conn.executescript(SCHEMA)
        migrations.migrate(self.conn)

    # ---------------------------------------------------------------- transactions

    def begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self.conn.execute("COMMIT")

    def rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def savepoint(self) -> None:
        self.conn.execute("SAVEPOINT esc_rule")

    def rollback_to_savepoint(self) -> None:
        self.conn.execute("ROLLBACK TO SAVEPOINT esc_rule")

    def release_savepoint(self) -> None:
        self.conn.execute("RELEASE SAVEPOINT esc_rule")

    # ---------------------------------------------------------------- rules and audit

    def rule_document(self, rule_id: str, include_deleted: bool = False) -> dict | None:
        """The saved rule's document, or None. A deleted rule counts only if `include_deleted` is True."""
        row = self.conn.execute("SELECT document, deleted_at FROM esc_rules WHERE rule_id = ?", (rule_id,)).fetchone()
        if row is None or (row[1] is not None and not include_deleted):
            return None
        return json.loads(row[0])

    def rule_documents(self, project_id: int) -> list[dict]:
        """The project's live rules, in rule ID order. Deleted rules are not evaluated (spec 1.2.0, B8)."""
        rows = self.conn.execute("SELECT document FROM esc_rules WHERE project_id = ? AND deleted_at IS NULL "
                                 "ORDER BY rule_id", (project_id,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def is_deleted(self, rule_id: str) -> bool:
        row = self.conn.execute("SELECT deleted_at FROM esc_rules WHERE rule_id = ?", (rule_id,)).fetchone()
        return row is not None and row[0] is not None

    def delete_rule(self, rule_id: str, at: datetime) -> bool:
        """Mark a live rule deleted. True if this call deleted it; False if it was absent or already deleted.

        The row stays, so held emails and the audit log can still name the rule,
        and its ID cannot be reused (spec 1.2.0, B8).
        """
        # TODO (README step 4: one UPDATE; see the docstring)
        raise NotImplementedError("TODO: EscalationStore.delete_rule (README step 4: one UPDATE; see the docstring)")

    def put_rule(self, rule: Rule, document: dict, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO esc_rules (rule_id, project_id, priority, document, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(rule_id) DO UPDATE SET project_id = excluded.project_id, priority = excluded.priority, "
            "document = excluded.document, updated_at = excluded.updated_at",
            (rule.rule_id, rule.project_id, rule.priority, json.dumps(document, sort_keys=True), ts(at)))

    def add_audit(self, at: datetime, actor_id: int, rule_id: str, outcome: str, code: str | None = None,
                  before: dict | None = None, after: dict | None = None, problems: list | None = None) -> None:
        self.conn.execute(
            "INSERT INTO esc_audit (at, actor_id, rule_id, outcome, code, before, after, problems) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ts(at), actor_id, rule_id, outcome, code, *(None if v is None else json.dumps(v, sort_keys=True)
                                                       for v in (before, after, problems))))

    def audit(self, rule_id: str | None = None) -> list[AuditEntry]:
        sql = "SELECT id, at, actor_id, rule_id, outcome, code, before, after, problems FROM esc_audit"
        rows = self.conn.execute(sql + (" WHERE rule_id = ? ORDER BY id" if rule_id else " ORDER BY id"),
                                 (rule_id,) if rule_id else ()).fetchall()
        return [AuditEntry(r[0], dt(r[1]), r[2], r[3], r[4], r[5],
                           *(None if v is None else json.loads(v) for v in r[6:9])) for r in rows]

    # ---------------------------------------------------------------- per-task state

    def ensure_state(self, task_id: int, project_id: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO esc_state (task_id, project_id) VALUES (?, ?)", (task_id, project_id))

    def state(self, task_id: int) -> EscalationState:
        row = self.conn.execute(
            "SELECT priority, priority_set_at, suggested_priority, suggested_confidence, acknowledged_at "
            "FROM esc_state WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return EscalationState(task_id=task_id)
        return EscalationState(task_id, row[0], dt(row[1]), row[2], row[3], dt(row[4]))

    def state_people(self, task_id: int) -> tuple[int | None, int | None]:
        """(who set the priority, who acknowledged)."""
        row = self.conn.execute("SELECT priority_set_by, acknowledged_by FROM esc_state WHERE task_id = ?",
                                (task_id,)).fetchone()
        return (None, None) if row is None else (row[0], row[1])

    def set_priority(self, task_id: int, priority: str, by: int, at: datetime) -> None:
        self.conn.execute("UPDATE esc_state SET priority = ?, priority_set_at = ?, priority_set_by = ? "
                          "WHERE task_id = ?", (priority, ts(at), by, task_id))

    def set_suggestion(self, task_id: int, priority: str, confidence: int) -> None:
        self.conn.execute("UPDATE esc_state SET suggested_priority = ?, suggested_confidence = ? WHERE task_id = ?",
                          (priority, confidence, task_id))

    def set_acknowledged(self, task_id: int, by: int, at: datetime) -> bool:
        cur = self.conn.execute("UPDATE esc_state SET acknowledged_at = ?, acknowledged_by = ? "
                                "WHERE task_id = ? AND acknowledged_at IS NULL", (ts(at), by, task_id))
        return cur.rowcount == 1

    def live_tasks(self) -> list[tuple[int, int]]:
        """(task_id, project_id) with a person-set priority and no acknowledgement, in task order."""
        return self.conn.execute("SELECT task_id, project_id FROM esc_state WHERE priority IS NOT NULL "
                                 "AND acknowledged_at IS NULL ORDER BY task_id").fetchall()

    # ---------------------------------------------------------------- fired steps, activity, outbox

    def fired_steps(self, task_id: int, rule_id: str) -> frozenset[int]:
        rows = self.conn.execute("SELECT step FROM esc_fired WHERE task_id = ? AND rule_id = ?",
                                 (task_id, rule_id)).fetchall()
        return frozenset(r[0] for r in rows)

    def mark_fired(self, task_id: int, rule_id: str, step: int, at: datetime) -> bool:
        """True if this call fired the step; False if it had already fired (D9)."""
        cur = self.conn.execute("INSERT OR IGNORE INTO esc_fired (task_id, rule_id, step, fired_at) "
                                "VALUES (?, ?, ?, ?)",
                                (task_id, rule_id, step, ts(at)))
        return cur.rowcount == 1

    def add_activity(self, task_id: int, at: datetime, kind: str, detail: dict) -> None:
        self.conn.execute("INSERT INTO esc_activity (task_id, at, kind, detail) VALUES (?, ?, ?, ?)",
                          (task_id, ts(at), kind, json.dumps(detail, sort_keys=True)))

    def activity(self, task_id: int) -> list[dict]:
        rows = self.conn.execute("SELECT at, kind, detail FROM esc_activity WHERE task_id = ? ORDER BY id",
                                 (task_id,)).fetchall()
        return [{"at": r[0], "kind": r[1], **json.loads(r[2])} for r in rows]

    def add_outbox(self, key: str, at: datetime, channel: str, kind: str, recipient: str, headers: dict,
                   body: str) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO esc_outbox (dedupe_key, created_at, channel, kind, recipient, headers, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", (key, ts(at), channel, kind, recipient, json.dumps(headers, sort_keys=True),
                                             body))
        return cur.rowcount == 1

    def outbox(self) -> list[OutboxItem]:
        rows = self.conn.execute("SELECT id, created_at, channel, kind, recipient, headers, body FROM esc_outbox "
                                 "ORDER BY id").fetchall()
        return [OutboxItem(r[0], dt(r[1]), r[2], r[3], r[4], json.loads(r[5]), r[6]) for r in rows]

    def escalation_emails_since(self, user_id: int, since: datetime) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM esc_outbox WHERE channel = 'email' AND kind = 'escalation' "
                                "AND recipient = ? AND created_at > ?", (str(user_id), ts(since))).fetchone()
        return row[0]

    # ---------------------------------------------------------------- the flood cap's held emails

    def hold(self, target_id: int, task_id: int, rule_id: str, step: int, at: datetime,
             summary_due_at: datetime) -> None:
        self.conn.execute("INSERT OR IGNORE INTO esc_held (target_id, task_id, rule_id, step, held_at, summary_due_at) "
                          "VALUES (?, ?, ?, ?, ?, ?)", (target_id, task_id, rule_id, step, ts(at), ts(summary_due_at)))

    def summaries_due(self, now: datetime) -> list[tuple[int, datetime, list[tuple[int, str, int]]]]:
        """[(target, hour_ends, [(task_id, rule_id, step), ...])] for held emails whose hour has ended."""
        rows = self.conn.execute("SELECT target_id, summary_due_at, task_id, rule_id, step FROM esc_held "
                                 "WHERE summarized = 0 AND summary_due_at <= ? ORDER BY target_id, summary_due_at, id",
                                 (ts(now),)).fetchall()
        grouped: dict[tuple[int, str], list[tuple[int, str, int]]] = {}
        for target, due, task_id, rule_id, step in rows:
            grouped.setdefault((target, due), []).append((task_id, rule_id, step))
        return [(target, dt(due), items) for (target, due), items in grouped.items()]

    def mark_summarized(self, target_id: int, hour_ends: datetime) -> None:
        self.conn.execute("UPDATE esc_held SET summarized = 1 WHERE target_id = ? AND summary_due_at = ?",
                          (target_id, ts(hour_ends)))

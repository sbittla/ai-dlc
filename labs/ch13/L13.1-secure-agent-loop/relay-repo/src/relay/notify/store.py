"""Notification preferences on SQLite: the new tables, and the legacy table kept in step (4.22.0; ADR-018).

New tables (PR notify-3), owned by this module:

    notify_optouts      (user_id, type): one row per muted type, lower case
    notify_spam_marks   (user_id, marked_on): the UTC date of a spam mark

The legacy table `notification_prefs` (Relay 3.x) is kept and written on every
change, in the same transaction as the new tables, until the rollback window
closes on 2027-01-31 (ADR-018). Rolling back reads is then a configuration
change, not a restore. Nothing here drops or rewrites a legacy row except to
apply the same change the new tables receive.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from .decide import Prefs, parse_muted

SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_prefs (
    user_id        INTEGER PRIMARY KEY,
    muted_types    TEXT,
    spam_marked_on TEXT
);
CREATE TABLE IF NOT EXISTS notify_optouts (
    user_id INTEGER NOT NULL,
    type    TEXT NOT NULL,
    PRIMARY KEY (user_id, type)
);
CREATE TABLE IF NOT EXISTS notify_spam_marks (
    user_id   INTEGER PRIMARY KEY,
    marked_on TEXT NOT NULL
);
"""


class NotifyStore:
    """Preferences for one workspace database. Pass a path or an open connection."""

    def __init__(self, db: str | sqlite3.Connection = ":memory:") -> None:
        self.conn = db if isinstance(db, sqlite3.Connection) else sqlite3.connect(db, isolation_level=None)
        self.conn.executescript(SCHEMA)
        self.shadow_differences: list[tuple[int, Prefs, Prefs]] = []  # (user, legacy, new) in shadow reads

    # ------------------------------------------------------------ reads

    def prefs(self, user_id: int) -> Prefs:
        """From the new tables."""
        muted = frozenset(r[0] for r in self.conn.execute(
            "SELECT type FROM notify_optouts WHERE user_id = ?", (user_id,)))
        row = self.conn.execute("SELECT marked_on FROM notify_spam_marks WHERE user_id = ?", (user_id,)).fetchone()
        return Prefs(muted, None if row is None else date.fromisoformat(row[0]))

    def legacy_prefs(self, user_id: int) -> Prefs:
        """From the legacy table, read as the legacy code read it."""
        row = self.conn.execute("SELECT muted_types, spam_marked_on FROM notification_prefs WHERE user_id = ?",
                                (user_id,)).fetchone()
        if row is None:
            return Prefs()
        return Prefs(parse_muted(row[0]), date.fromisoformat(row[1]) if row[1] else None)

    def legacy_users(self) -> list[int]:
        return [r[0] for r in self.conn.execute("SELECT user_id FROM notification_prefs ORDER BY user_id")]

    def counts(self) -> dict[str, int]:
        return {name: self.conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in ("notification_prefs", "notify_optouts", "notify_spam_marks")}

    # ------------------------------------------------------------ writes (both tables, one transaction)

    def set_muted(self, user_id: int, types: list[str]) -> None:
        clean = sorted({t.strip().lower() for t in types if t.strip()})
        self._write(
            ("DELETE FROM notify_optouts WHERE user_id = ?", (user_id,)),
            *[("INSERT INTO notify_optouts (user_id, type) VALUES (?, ?)", (user_id, t)) for t in clean],
            ("INSERT INTO notification_prefs (user_id, muted_types) VALUES (?, ?) ON CONFLICT(user_id) "
             "DO UPDATE SET muted_types = excluded.muted_types", (user_id, ",".join(types))),
        )

    def mark_spam(self, user_id: int, on: date) -> None:
        self._write(
            ("INSERT INTO notify_spam_marks (user_id, marked_on) VALUES (?, ?) ON CONFLICT(user_id) "
             "DO UPDATE SET marked_on = excluded.marked_on", (user_id, on.isoformat())),
            ("INSERT INTO notification_prefs (user_id, spam_marked_on) VALUES (?, ?) ON CONFLICT(user_id) "
             "DO UPDATE SET spam_marked_on = excluded.spam_marked_on", (user_id, on.isoformat())),
        )

    def clear_spam(self, user_id: int) -> None:
        self._write(("DELETE FROM notify_spam_marks WHERE user_id = ?", (user_id,)),
                    ("UPDATE notification_prefs SET spam_marked_on = NULL WHERE user_id = ?", (user_id,)))

    def _write(self, *statements: tuple[str, tuple]) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for sql, params in statements:
                self.conn.execute(sql, params)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

"""Copy the legacy preferences into the new tables, and prove the copy (4.22.0, PR notify-3; ADR-018, ADR-019).

The copy runs in one transaction. Before it commits, it checks every legacy
user: the preferences read from the new tables must equal the preferences the
legacy code would read from the legacy row. Any difference rolls the whole
copy back. The legacy table is read, never altered and never dropped, so the
rollback for this migration is to stop reading the new tables.

Two mistakes this guards against are the ones in the opening incident of
Chapter 9: splitting the legacy list on "," only, when Relay 3.0 to 3.3 wrote
"a;b", and filtering rows with `muted_types <> ''`, which in SQL is never true
for a NULL and so drops every user who has a spam mark but no muted types.
"""

from __future__ import annotations

from dataclasses import dataclass

from .decide import parse_muted
from .store import NotifyStore


class NotifyMigrationRefused(RuntimeError):
    """The new tables already hold rows, or the copy did not match; nothing was changed."""


@dataclass(frozen=True)
class MigrationReport:
    legacy_users: int
    optouts: int
    spam_marks: int
    mismatches: int  # users whose new preferences differ from their legacy ones; 0, or the copy is refused


def migrate_legacy(store: NotifyStore) -> MigrationReport:
    conn = store.conn
    conn.execute("BEGIN IMMEDIATE")
    try:
        counts = store.counts()
        if counts["notify_optouts"] or counts["notify_spam_marks"]:
            raise NotifyMigrationRefused("the new tables already hold rows: the copy has run, or writes began")
        rows = conn.execute("SELECT user_id, muted_types, spam_marked_on FROM notification_prefs "
                            "ORDER BY user_id").fetchall()  # every row: no WHERE clause
        for user_id, muted_types, spam_marked_on in rows:
            for ntype in sorted(parse_muted(muted_types)):
                conn.execute("INSERT INTO notify_optouts (user_id, type) VALUES (?, ?)", (user_id, ntype))
            if spam_marked_on:
                conn.execute("INSERT INTO notify_spam_marks (user_id, marked_on) VALUES (?, ?)",
                             (user_id, spam_marked_on))
        mismatches = sum(1 for (user_id, *_rest) in rows if store.prefs(user_id) != store.legacy_prefs(user_id))
        if mismatches:
            raise NotifyMigrationRefused(f"{mismatches} user(s) would change preferences; nothing was copied")
        after = store.counts()
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return MigrationReport(len(rows), after["notify_optouts"], after["notify_spam_marks"], 0)

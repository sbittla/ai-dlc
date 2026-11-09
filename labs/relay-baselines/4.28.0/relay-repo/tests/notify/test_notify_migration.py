"""The legacy preferences migration (PR notify-3; ADR-018, ADR-019).

The two rows at the top are the shapes the opening incident of Chapter 9 lost:
a 3.x list written with ";" and a spam mark on a user with no muted types.
"""

from datetime import date

import pytest

from relay.notify.decide import Prefs
from relay.notify.migrate import NotifyMigrationRefused, migrate_legacy
from relay.notify.store import NotifyStore

ROWS = [
    (1001, "comment;mention", None),  # Relay 3.0 to 3.3 format
    (1002, None, "2026-12-01"),  # spam mark, no muted types: `muted_types <> ''` is not true for NULL
    (1003, "digest,due_soon", "2026-11-20"),
    (1004, "", None),
]


def legacy_store():
    store = NotifyStore()
    store.conn.executemany("INSERT INTO notification_prefs VALUES (?, ?, ?)", ROWS)
    return store


def test_every_legacy_user_keeps_their_preferences():
    store = legacy_store()
    report = migrate_legacy(store)
    assert (report.legacy_users, report.optouts, report.spam_marks, report.mismatches) == (4, 4, 2, 0)
    assert store.prefs(1001) == Prefs(frozenset({"comment", "mention"}))
    assert store.prefs(1002) == Prefs(frozenset(), date(2026, 12, 1))


def test_the_legacy_table_is_never_altered_or_dropped():
    store = legacy_store()
    migrate_legacy(store)
    assert store.conn.execute("SELECT * FROM notification_prefs ORDER BY user_id").fetchall() == ROWS


def test_a_second_run_is_refused_rather_than_duplicating_rows():
    store = legacy_store()
    migrate_legacy(store)
    with pytest.raises(NotifyMigrationRefused):
        migrate_legacy(store)
    assert store.counts() == {"notification_prefs": 4, "notify_optouts": 4, "notify_spam_marks": 2}


def test_a_copy_that_would_change_a_users_preferences_is_refused_and_nothing_is_copied(monkeypatch):
    import relay.notify.migrate as migrate

    def comma_only(text):  # the incident's split: "a;b" becomes one unknown type
        return frozenset(t.strip().lower() for t in (text or "").split(",") if t.strip())

    store = legacy_store()
    monkeypatch.setattr(migrate, "parse_muted", comma_only)
    with pytest.raises(NotifyMigrationRefused):
        migrate_legacy(store)
    assert store.counts() == {"notification_prefs": 4, "notify_optouts": 0, "notify_spam_marks": 0}


def test_writes_after_the_migration_reach_both_tables_in_one_transaction():
    store = legacy_store()
    migrate_legacy(store)
    store.set_muted(1004, ["Assignment"])
    store.mark_spam(1004, date(2026, 12, 16))
    assert store.prefs(1004) == store.legacy_prefs(1004) == Prefs(frozenset({"assignment"}), date(2026, 12, 16))

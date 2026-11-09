"""Relay's notification preferences, modernized behind a compatibility layer (4.22.0; ADR-018).

Production code written for Relay 3.x calls the legacy functions by name:
`init`, `get_prefs`, `mute`, `mark_spam`, `clear_spam` and `should_send`. They
keep their names, arguments and results here, except one recorded difference:
`get_prefs` lists muted types sorted and without duplicates (ADR-018).
Underneath, the decision is a pure function (`decide`) and the data lives in
new tables (`NotifyStore`), with the legacy table kept in step for rollback.

READ_FROM chooses where decisions read preferences. It is read from the
environment variable RELAY_NOTIFY_READ_FROM when the module is imported, so
rolling reads back is a configuration change and a restart, not a deploy:

    "new"     the new tables (from PR notify-5)
    "shadow"  both; the legacy answer is returned and any difference recorded (PR notify-4)
    "legacy"  the legacy table only: the rollback, until 2027-01-31

New code should take a NotifyStore and call `decide` directly; the functions
below exist for callers that cannot change yet.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .decide import SPAM_DAYS, TYPES, Decision, Prefs, decide, parse_muted
from .migrate import MigrationReport, NotifyMigrationRefused, migrate_legacy
from .store import NotifyStore

READ_FROM = os.environ.get("RELAY_NOTIFY_READ_FROM", "shadow")  # set it to "legacy" to roll reads back
READ_MODES = ("new", "shadow", "legacy")

_store: NotifyStore | None = None


def init(path: str = ":memory:") -> NotifyStore:
    global _store
    _store = NotifyStore(path)
    return _store


def _active() -> NotifyStore:
    if _store is None:
        raise RuntimeError("call relay.notify.init(path) first, as the legacy module required")
    return _store


def _when(now: datetime | None) -> datetime:
    """The time as the legacy code used it: the current UTC time if none is given, and otherwise unchanged.

    The legacy code took the date of the time it was given, so an aware time
    counts in its own zone's date, not UTC's. That is characterized, not
    endorsed (ADR-018): converting to UTC here would change which day a spam
    mark expires on for callers that pass zoned times.
    """
    return datetime.now(timezone.utc) if now is None else now


def get_prefs(user_id: int) -> dict:
    prefs = _read(user_id)
    return {"muted": sorted(prefs.muted),
            "spam_marked_on": None if prefs.spam_marked_on is None else prefs.spam_marked_on.isoformat()}


def mute(user_id: int, types: list[str]) -> None:
    _active().set_muted(user_id, list(types))


def mark_spam(user_id: int, when: datetime | None = None) -> None:
    _active().mark_spam(user_id, _when(when).date())


def clear_spam(user_id: int) -> None:
    _active().clear_spam(user_id)


def should_send(user_id: int, ntype: str, now: datetime | None = None) -> bool:
    return decide(_read(user_id), ntype, _when(now)).send


def _read(user_id: int) -> Prefs:
    store = _active()
    if READ_FROM not in READ_MODES:
        raise ValueError(f"READ_FROM must be one of {READ_MODES}")
    if READ_FROM == "legacy":
        return store.legacy_prefs(user_id)
    if READ_FROM == "new":
        return store.prefs(user_id)
    legacy, new = store.legacy_prefs(user_id), store.prefs(user_id)
    if legacy != new:
        store.shadow_differences.append((user_id, legacy, new))
    return legacy


__all__ = ["READ_FROM", "READ_MODES", "SPAM_DAYS", "TYPES", "Decision", "MigrationReport", "NotifyMigrationRefused",
           "NotifyStore", "Prefs", "clear_spam", "decide", "get_prefs", "init", "mark_spam",
           "migrate_legacy", "mute", "parse_muted", "should_send"]

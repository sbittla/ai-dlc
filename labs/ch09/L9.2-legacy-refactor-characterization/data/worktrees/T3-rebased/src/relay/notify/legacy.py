# Provenance: Relay production repository, relay/notifications.py, Relay 3.9 (last changed 2024-03-12).
# Imported unchanged on 2026-12-14 (PR notify-1, ADR-018). This is the working copy, modernized in place by
# notify-2 and notify-3 and retired by notify-5; tests/notify/legacy_reference.py is the frozen copy.
"""Notification preferences, written to the legacy table and the new tables (notify-3).

The send decision is in decide.py (notify-2).
"""
import re
import sqlite3
from datetime import datetime

from .decide import Prefs, decide
from .store import NotifyStore

TYPES = ("mention", "assignment", "comment", "due_soon", "digest", "security")
SPAM_DAYS = 30

_db = None
_store = None  # notify-3: the new tables, written in the same transaction as the legacy one


def init(path=":memory:"):
    global _db, _store
    _db = sqlite3.connect(path)
    _db.execute("CREATE TABLE IF NOT EXISTS notification_prefs "
                "(user_id INTEGER PRIMARY KEY, muted_types TEXT, spam_marked_on TEXT)")
    _db.commit()
    _store = NotifyStore(_db)
    return _db


def get_prefs(user_id):
    row = _db.execute("SELECT muted_types, spam_marked_on FROM notification_prefs WHERE user_id = ?",
                      (user_id,)).fetchone()
    if row is None:
        return {"muted": [], "spam_marked_on": None}
    # 3.0 to 3.3 wrote "a;b"; 3.4 and later write "a,b"
    muted = [t.strip().lower() for t in re.split("[;,]", row[0] or "") if t.strip()]
    return {"muted": muted, "spam_marked_on": row[1]}


def mute(user_id, types):
    _store.set_muted(user_id, list(types))


def mark_spam(user_id, when=None):
    when = when or datetime.utcnow()
    _store.mark_spam(user_id, when.date())


def clear_spam(user_id):
    _store.clear_spam(user_id)


def should_send(user_id, ntype, now=None):
    now = now or datetime.utcnow()
    p = get_prefs(user_id)
    marked = datetime.strptime(p["spam_marked_on"], "%Y-%m-%d").date() if p["spam_marked_on"] else None
    return decide(Prefs(frozenset(p["muted"]), marked), ntype, now).send  # notify-2: the rules live in decide.py

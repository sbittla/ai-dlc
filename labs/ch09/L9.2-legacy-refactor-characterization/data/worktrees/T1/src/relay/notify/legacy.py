# Provenance: Relay production repository, relay/notifications.py, Relay 3.9 (last changed 2024-03-12).
# Imported unchanged on 2026-12-14 (PR notify-1, ADR-018). This is the working copy, modernized in place by
# notify-2 and notify-3 and retired by notify-5; tests/notify/legacy_reference.py is the frozen copy.
"""Notification preferences and the send decision."""
import re
import sqlite3
from datetime import datetime

TYPES = ("mention", "assignment", "comment", "due_soon", "digest", "security")
SPAM_DAYS = 30

_db = None


def init(path=":memory:"):
    global _db
    _db = sqlite3.connect(path)
    _db.execute("CREATE TABLE IF NOT EXISTS notification_prefs "
                "(user_id INTEGER PRIMARY KEY, muted_types TEXT, spam_marked_on TEXT)")
    _db.commit()
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
    _db.execute("INSERT INTO notification_prefs (user_id, muted_types) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET muted_types = excluded.muted_types", (user_id, ",".join(types)))
    _db.commit()


def mark_spam(user_id, when=None):
    when = when or datetime.utcnow()
    _db.execute("INSERT INTO notification_prefs (user_id, spam_marked_on) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET spam_marked_on = excluded.spam_marked_on",
                (user_id, when.strftime("%Y-%m-%d")))
    _db.commit()


def clear_spam(user_id):
    _db.execute("UPDATE notification_prefs SET spam_marked_on = NULL WHERE user_id = ?", (user_id,))
    _db.commit()


def should_send(user_id, ntype, now=None):
    now = now or datetime.utcnow()
    p = get_prefs(user_id)
    if p["spam_marked_on"]:
        marked = datetime.strptime(p["spam_marked_on"], "%Y-%m-%d").date()
        if (now.date() - marked).days < SPAM_DAYS:
            return False
    if ntype == "security":
        return True
    if "all" in p["muted"]:
        return False
    return ntype not in p["muted"]

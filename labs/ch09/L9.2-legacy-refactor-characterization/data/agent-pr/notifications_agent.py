# Reconstructed for the book's composite incident (Chapter 9): the send decision and preference reads from agent
# pull request #2291, condensed to the legacy module's public functions so the characterization tests can run it.
# Input data for Lab 9.2. Its three changes in behaviour were not in the pull request's description.
"""Notification preferences, rewritten (agent pull request #2291)."""
import sqlite3
from datetime import date, datetime, time, timedelta

from migrate_notifications import upgrade

TYPES = ("mention", "assignment", "comment", "due_soon", "digest", "security")
SPAM_DAYS = 30

_db = None


def init(path=":memory:"):
    global _db
    _db = sqlite3.connect(path)
    _db.execute("CREATE TABLE IF NOT EXISTS notification_prefs "
                "(user_id INTEGER PRIMARY KEY, muted_types TEXT, spam_marked_on TEXT)")
    return _db


def migrate():
    upgrade(_db)


def get_prefs(user_id):
    muted = sorted(r[0] for r in _db.execute("SELECT type FROM notify_optouts WHERE user_id = ?", (user_id,)))
    row = _db.execute("SELECT marked_on FROM notify_spam_marks WHERE user_id = ?", (user_id,)).fetchone()
    return {"muted": muted, "spam_marked_on": row[0] if row else None}


def should_send(user_id, ntype, now=None):
    now = now or datetime.utcnow()
    p = get_prefs(user_id)
    if ntype == "security":  # security notices always go out
        return True
    if p["spam_marked_on"]:
        marked = datetime.combine(date.fromisoformat(p["spam_marked_on"]), time())
        if now - marked <= timedelta(days=SPAM_DAYS):
            return False
    if ntype not in TYPES:  # ignore types we do not know
        return False
    return "all" not in p["muted"] and ntype not in p["muted"]

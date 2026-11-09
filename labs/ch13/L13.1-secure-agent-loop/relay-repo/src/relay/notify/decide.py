"""Whether Relay may send a user a notification: a pure decision (4.22.0, PR notify-2; ADR-018).

Extracted from the legacy module's `should_send` without changing what it
decides. The characterization tests compare this code with the legacy module,
kept unchanged in tests/notify/legacy_reference.py, on generated cases. The
rules, in order, as the legacy code applied them:

1. A spam mark suppresses every notification, security notices included, until
   30 calendar days have passed, counted in whole dates: a mark dated
   1 December suppresses through 30 December and expires on 31 December. The
   date is the date of the time given: for a naive (UTC) time, the UTC date;
   for an aware time, the date in that time's own zone. A mark made with an
   aware time is dated in its zone too. Characterized, not endorsed.
2. Security notices are always sent otherwise; they cannot be muted.
3. "all" in the muted list mutes every other type.
4. Otherwise a type is sent unless it is muted. Unknown types are sent.

Rule 1's suppression of security notices is characterized, not endorsed.
Changing it is a behaviour change, with its own spec and pull request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

TYPES = ("mention", "assignment", "comment", "due_soon", "digest", "security")
SPAM_DAYS = 30


@dataclass(frozen=True)
class Prefs:
    """One user's preferences: muted types (lower case) and the UTC date of a spam mark, if any."""

    muted: frozenset[str] = frozenset()
    spam_marked_on: date | None = None


@dataclass(frozen=True)
class Decision:
    send: bool
    reason: str  # spam_mark | security | muted_all | muted | not_muted


def parse_muted(text: str | None) -> frozenset[str]:
    """The legacy `muted_types` column: "a;b" (Relay 3.0 to 3.3) or "a,b" (3.4 on), any case, blanks ignored."""
    return frozenset(t.strip().lower() for t in re.split("[;,]", text or "") if t.strip())


def decide(prefs: Prefs, ntype: str, now: datetime) -> Decision:
    """The decision for one notification of type `ntype` at `now` (UTC). Reads no clock and no database."""
    if prefs.spam_marked_on is not None and (now.date() - prefs.spam_marked_on).days < SPAM_DAYS:
        return Decision(False, "spam_mark")
    if ntype == "security":
        return Decision(True, "security")
    if "all" in prefs.muted:
        return Decision(False, "muted_all")
    if ntype in prefs.muted:
        return Decision(False, "muted")
    return Decision(True, "not_muted")

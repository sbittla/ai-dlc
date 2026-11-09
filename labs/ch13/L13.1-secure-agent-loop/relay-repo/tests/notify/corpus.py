"""Generated cases for characterizing the notification module (PR notify-1; ADR-018).

A case is a stored preference row, a notification type and a time. The rows
are shaped like production's: lists written by Relay 3.0 to 3.3 ("a;b") and by
3.4 and later ("a,b"), mixed case, duplicates, "all", empty and NULL lists,
spam marks with and without muted types, and users with no row at all. Times
sit on both sides of the 30-day spam boundary, and some are timezone-aware
(UTC+14:00 and UTC-11:00), as callers that pass zoned times produce. Write
sequences (mute, mark_spam, clear_spam) are characterized separately. Seeded,
so every run checks the same cases; set NOTIFY_SEED to try others.

Tags name the behaviour a case exercises, so a difference can be reported by
behaviour rather than by case number.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

TYPES = ("mention", "assignment", "comment", "due_soon", "digest", "security")
CASE_TYPES = TYPES + ("billing_alert",)  # one type the module has never heard of
SEED = int(os.environ.get("NOTIFY_SEED", "9"))
STATES = 160
SEQUENCES = 40
PLUS_14 = timezone(timedelta(hours=14))
MINUS_11 = timezone(timedelta(hours=-11))


@dataclass(frozen=True)
class State:
    user_id: int
    row: bool  # False: the user has no row at all
    muted_types: str | None  # the raw column, exactly as stored
    spam_marked_on: str | None  # "YYYY-MM-DD" or None


@dataclass(frozen=True)
class Case:
    state: State
    ntype: str
    now: datetime  # naive UTC, as the legacy code used, or aware (tag aware_time)
    tags: tuple[str, ...]


def _muted(rng: random.Random) -> str | None:
    roll = rng.random()
    if roll < 0.12:
        return None
    if roll < 0.18:
        return ""
    names = rng.sample(TYPES[:5] + ("all",), rng.randint(1, 3))
    if rng.random() < 0.15:
        names.append(names[0])  # a duplicate, which the settings page once allowed
    style = rng.choice((str.lower, str.lower, str.title, str.upper))
    sep = rng.choice((";", ",", ",", ", ", " ; "))
    return sep.join(style(n) for n in names)


def states(seed: int = SEED) -> list[State]:
    rng = random.Random(seed)
    out = []
    for i in range(STATES):
        uid = 1000 + i
        if i % 20 == 0:
            out.append(State(uid, False, None, None))
            continue
        spam = None
        if rng.random() < 0.45:
            spam = (date(2026, 11, 1) + timedelta(days=rng.randint(0, 49))).isoformat()
        out.append(State(uid, True, _muted(rng), spam))
    return out


def _times(state: State, rng: random.Random) -> list[datetime]:
    if state.spam_marked_on:
        marked = datetime.fromisoformat(state.spam_marked_on)
        day30 = marked + timedelta(days=30)
        return [marked + timedelta(days=29, hours=23, minutes=59), day30,
                marked + timedelta(days=rng.randint(0, 45), minutes=rng.randint(0, 1439)),
                day30.replace(hour=5, tzinfo=PLUS_14),  # day 30 in its zone, day 29 in UTC
                (day30 - timedelta(days=1)).replace(hour=20, tzinfo=MINUS_11)]  # day 29 in its zone, day 30 in UTC
    start = datetime(2026, 12, 1)
    times = [start + timedelta(minutes=rng.randint(0, 31 * 1440)) for _ in range(3)]
    return times + [times[0].replace(tzinfo=rng.choice((PLUS_14, MINUS_11)))]


def tags_for(state: State, ntype: str, now: datetime) -> tuple[str, ...]:
    tags = []
    raw = state.muted_types or ""
    if not state.row:
        tags.append("no_row")
    if ";" in raw:
        tags.append("semicolon_list")
    if raw != raw.lower():
        tags.append("mixed_case")
    if "all" in raw.lower():
        tags.append("muted_all")
    if state.spam_marked_on:
        tags.append("spam_mark")
        if state.muted_types in (None, ""):
            tags.append("spam_without_muted")
        days = (now.date() - date.fromisoformat(state.spam_marked_on)).days
        if days in (29, 30):
            tags.append("spam_boundary")
    if now.tzinfo is not None:
        tags.append("aware_time")
    if ntype == "security":
        tags.append("security")
    if ntype not in TYPES:
        tags.append("unknown_type")
    return tuple(tags)


def cases(seed: int = SEED) -> list[Case]:
    rng = random.Random(seed + 1)
    out = []
    for state in states(seed):
        for now in _times(state, rng):
            for ntype in CASE_TYPES:
                out.append(Case(state, ntype, now, tags_for(state, ntype, now)))
    return out


@dataclass(frozen=True)
class Sequence:
    user_id: int
    ops: tuple  # ("mute", [types]) | ("mark_spam", datetime) | ("clear_spam",)
    checks: tuple[datetime, ...]  # times at which every CASE_TYPE is decided after the ops


def sequences(seed: int = SEED) -> list[Sequence]:
    """Write sequences through the public functions, as callers make them: naive and aware times, mixed case."""
    rng = random.Random(seed + 2)
    out = []
    for i in range(SEQUENCES):
        ops = []
        for _ in range(rng.randint(1, 4)):
            kind = rng.choice(("mute", "mute", "mark_spam", "mark_spam", "clear_spam"))
            if kind == "mute":
                names = rng.sample(TYPES[:5] + ("all",), rng.randint(0, 3))
                if names and rng.random() < 0.3:
                    names.append(names[0].title())  # the same type twice, in two cases
                ops.append(("mute", names))
            elif kind == "mark_spam":
                when = datetime(2026, 12, 1) + timedelta(days=rng.randint(0, 20), minutes=rng.randint(0, 1439))
                ops.append(("mark_spam", when.replace(tzinfo=rng.choice((None, PLUS_14, MINUS_11)))))
            else:
                ops.append(("clear_spam",))
        base = datetime(2026, 12, 20) + timedelta(days=rng.randint(0, 25), minutes=rng.randint(0, 1439))
        out.append(Sequence(5000 + i, tuple(ops), (base, base.replace(tzinfo=PLUS_14), base.replace(tzinfo=MINUS_11))))
    return out


def apply(module, seq: Sequence) -> None:
    for op in seq.ops:
        getattr(module, op[0])(seq.user_id, *op[1:])

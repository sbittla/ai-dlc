"""The dated daylight-saving table, extended a year at a time from reviewed rules (added in 4.31.0; ADR-055).

ADR-010 gave business hours a table of daylight-saving periods for 14 zones in 2026 and 2027, failing closed
outside it, with a review due by 2027-09-30. Extending it is a bounded maintenance task (`table-extension`):

- the input is `maintenance/dst-rules.json`, rules a person reviewed (which Sunday, which UTC hour), not text
  from outside, so the task reads nothing untrusted;
- before proposing anything the bot recomputes the years already in the table from the same rules and
  requires every transition to match (`check_rules`): rules that cannot reproduce the reviewed years are not
  trusted for the next one;
- the change is a new block of periods and the moved end date, and nothing else (`extend`);
- tests that pin the table's old end are approved tests, owned by `@relay/security`; the bot lists them
  (`pinned_tests`) and never edits them, so the proposal goes to a person with that list.

A government can change its rules at short notice; the rules file, not this code, is what a person reviews.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
NAMES = ("_EU", "_NEW_YORK", "_LOS_ANGELES", "_SYDNEY", "_NEW_ZEALAND")


def _day(year: int, rule: dict) -> datetime:
    month, week = int(rule["month"]), rule["week"]
    days = [d for d in range(1, calendar.monthrange(year, month)[1] + 1)
            if calendar.weekday(year, month, d) == 6]  # Sundays
    pick = {"first": 0, "second": 1, "last": -1}[week]
    d = datetime(year, month, days[pick], int(rule["utc_hour"]), tzinfo=UTC)
    return d + timedelta(days=int(rule.get("day_shift", 0)))


def transitions(rules: dict, years: list[int]) -> dict[str, list[tuple[str, datetime]]]:
    """Every start and end instant per table, in time order."""
    out = {}
    for name in NAMES:
        r = rules["zones"][name]
        events = []
        for y in years:
            events += [("start", _day(y, r["start"])), ("end", _day(y, r["end"]))]
        out[name] = sorted(events, key=lambda e: e[1])
    return out


def periods(rules: dict, years: list[int], covered_from: datetime, covered_until: datetime):
    """[start, end) periods per table; a southern table's first and last periods run to the table's edges."""
    out = {}
    for name, events in transitions(rules, years).items():
        spans, start = [], covered_from if events[0][0] == "end" else None
        for kind, at in events:
            if kind == "start":
                start = at
            else:
                spans.append((start, at))
                start = None
        if start is not None:
            spans.append((start, covered_until))
        out[name] = tuple(spans)
    return out


def check_rules(rules: dict, table: dict, years: list[int], covered_from: datetime, covered_until: datetime):
    """(matching, total) transitions between the rules and the reviewed table for `years`."""
    ours = periods(rules, years, covered_from, covered_until)
    total = matching = 0
    for name in NAMES:
        want = [x for span in table[name] for x in span if covered_from < x < covered_until]
        got = [x for span in ours[name] for x in span if covered_from < x < covered_until]
        total += len(want)
        matching += sum(1 for a, b in zip(want, got) if a == b) if len(want) == len(got) else 0
    return matching, total


def _fmt(x: datetime, until_year: int) -> str:
    if x == datetime(2026, 1, 1, tzinfo=UTC):
        return "COVERED_FROM"
    if x == datetime(until_year, 1, 1, tzinfo=UTC):
        return "COVERED_UNTIL"
    return f"_z({x.year}, {x.month}, {x.day}, {x.hour})"


def block(rules: dict, last_year: int) -> str:
    years = list(range(2026, last_year + 1))
    until = datetime(last_year + 1, 1, 1, tzinfo=UTC)
    spans = periods(rules, years, datetime(2026, 1, 1, tzinfo=UTC), until)
    lines = []
    for name in NAMES:
        items = [f"({_fmt(a, last_year + 1)}, {_fmt(b, last_year + 1)})" for a, b in spans[name]]
        head = f"{name} = ("
        text, line = [], head
        for i, it in enumerate(items):
            piece = it + (", " if i < len(items) - 1 else ")")
            if len(line) + len(piece) > 118:
                text.append(line.rstrip())
                line = " " * len(head) + piece
            else:
                line += piece
        text.append(line)
        lines.append("\n".join(text))
    return "\n".join(lines)


_BLOCK = re.compile(r"^_EU = .*?^_NEW_ZEALAND = .*?\)\)\n", re.MULTILINE | re.DOTALL)


def extend(hours_text: str, rules: dict, new_last_year: int) -> str:
    """hours.py with the table running to the end of `new_last_year`, and its end date and messages moved."""
    old_last = new_last_year - 1
    text = hours_text.replace("\r\n", "\n")
    if len(_BLOCK.findall(text)) != 1:
        raise ValueError("the table block was not found exactly once")
    text = _BLOCK.sub(lambda _m: block(rules, new_last_year) + "\n", text)
    replacements = [
        (f"COVERED_UNTIL = datetime({old_last + 1}, 1, 1, tzinfo=UTC)",
         f"COVERED_UNTIL = datetime({new_last_year + 1}, 1, 1, tzinfo=UTC)"),
        (f"(2026-{old_last})", f"(2026-{new_last_year})"),
        (f"zones for 2026 and {old_last}", f"zones for 2026 to {new_last_year}"),
        (f"past {old_last}", f"past {new_last_year}")]
    for old, new in replacements:
        if old not in text:
            raise ValueError(f"expected text not found: {old}")
        text = text.replace(old, new)
    compile(text, "hours.py", "exec")
    return text


def pinned_tests(test_files: dict[str, str], old_last_year: int) -> list[str]:
    """Test files that mention the year after the table's old end, or say it covers exactly the old years.

    A deliberately simple search: it can list a file that needs no change, and a person reads the list.
    """
    marks = (f"{old_last_year + 1}", f"exactly_2026_and_{old_last_year}")
    return sorted(p for p, t in test_files.items() if any(m in t for m in marks))

"""Business hours: when a P2 to P4 rule's clock runs (spec ESC-SPEC-1 1.1.0, behaviour B3; ADR-010).

A rule's business hours are local wall-clock hours in the rule's own time zone
(D4), on the ISO weekdays the rule lists (D10). A business minute is a real,
elapsed minute that falls inside such a window. A step is due at the instant
its delay's business minutes have elapsed since the priority was set; if that
happens exactly as a window closes, the step is due at the close, not at the
next opening.

Time zones. Relay's snapshot avoids the `tzdata` package (relay.timezones keeps
one mid-November offset per zone). Business hours need the offset in force on
each date, so this module carries the daylight-saving periods of the same 14
zones for 2026 and 2027, as UTC instants. Outside those years it raises
ValueError instead of guessing (ADR-010). Production Relay uses IANA data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from .model import WEEKDAYS, BusinessHours

UTC = timezone.utc
COVERED_FROM = datetime(2026, 1, 1, tzinfo=UTC)
COVERED_UNTIL = datetime(2028, 1, 1, tzinfo=UTC)
HHMM = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def _z(y: int, mo: int, d: int, h: int) -> datetime:
    return datetime(y, mo, d, h, tzinfo=UTC)


_EU = ((_z(2026, 3, 29, 1), _z(2026, 10, 25, 1)), (_z(2027, 3, 28, 1), _z(2027, 10, 31, 1)))
_NEW_YORK = ((_z(2026, 3, 8, 7), _z(2026, 11, 1, 6)), (_z(2027, 3, 14, 7), _z(2027, 11, 7, 6)))
_LOS_ANGELES = ((_z(2026, 3, 8, 10), _z(2026, 11, 1, 9)), (_z(2027, 3, 14, 10), _z(2027, 11, 7, 9)))
_SYDNEY = ((COVERED_FROM, _z(2026, 4, 4, 16)), (_z(2026, 10, 3, 16), _z(2027, 4, 3, 16)),
           (_z(2027, 10, 2, 16), COVERED_UNTIL))
_NEW_ZEALAND = ((COVERED_FROM, _z(2026, 4, 4, 14)), (_z(2026, 9, 26, 14), _z(2027, 4, 3, 14)),
                (_z(2027, 9, 25, 14), COVERED_UNTIL))


@dataclass(frozen=True)
class Zone:
    standard: int  # minutes east of UTC
    daylight: int | None = None  # minutes east of UTC while daylight-saving time is in force
    daylight_periods: tuple[tuple[datetime, datetime], ...] = ()  # [start, end) in UTC


ZONES: dict[str, Zone] = {
    "Pacific/Pago_Pago": Zone(-11 * 60),
    "Pacific/Honolulu": Zone(-10 * 60),
    "America/Los_Angeles": Zone(-8 * 60, -7 * 60, _LOS_ANGELES),
    "America/New_York": Zone(-5 * 60, -4 * 60, _NEW_YORK),
    "UTC": Zone(0),
    "Europe/London": Zone(0, 60, _EU),
    "Europe/Berlin": Zone(60, 120, _EU),
    "Asia/Kolkata": Zone(5 * 60 + 30),
    "Asia/Tokyo": Zone(9 * 60),
    "Australia/Sydney": Zone(10 * 60, 11 * 60, _SYDNEY),
    "Pacific/Auckland": Zone(12 * 60, 13 * 60, _NEW_ZEALAND),
    "Pacific/Tongatapu": Zone(13 * 60),
    "Pacific/Chatham": Zone(12 * 60 + 45, 13 * 60 + 45, _NEW_ZEALAND),
    "Pacific/Kiritimati": Zone(14 * 60),
}


def offset_at(zone_name: str, instant: datetime) -> int:
    """Minutes east of UTC in force in `zone_name` at `instant` (aware). ValueError outside 2026-2027."""
    if instant.utcoffset() is None:
        raise ValueError("instant must be an aware datetime")
    if not COVERED_FROM <= instant < COVERED_UNTIL:
        raise ValueError(f"{instant.isoformat()} is outside the years the zone table covers (2026-2027)")
    zone = ZONES[zone_name]
    for start, end in zone.daylight_periods:
        if start <= instant < end:
            return zone.daylight
    return zone.standard


def to_local(zone_name: str, instant: datetime) -> datetime:
    """`instant` as naive local wall-clock time in `zone_name`."""
    return (instant.astimezone(UTC) + timedelta(minutes=offset_at(zone_name, instant))).replace(tzinfo=None)


def to_utc(zone_name: str, local: datetime) -> datetime:
    """The UTC instant of naive local wall-clock time `local`.

    In a repeated hour (clocks go back) the first occurrence is used; a local
    time that never happens (clocks go forward) is read with the standard offset.
    """
    zone = ZONES[zone_name]
    offsets = [zone.standard] + ([zone.daylight] if zone.daylight is not None else [])
    candidates = sorted(local.replace(tzinfo=UTC) - timedelta(minutes=m) for m in offsets)
    for instant in candidates:
        if to_local(zone_name, instant) == local:
            return instant
    return local.replace(tzinfo=UTC) - timedelta(minutes=zone.standard)


def _minutes(hhmm: str) -> int:
    m = HHMM.match(hhmm)
    return int(m[1]) * 60 + int(m[2])


def business_hours_problem(hours: BusinessHours) -> str | None:
    """Why `hours` cannot be used, or None. Used by validate_rule (code business_hours_invalid)."""
    if hours.time_zone not in ZONES:
        return f"time zone {hours.time_zone!r} is not supported"
    for label, value in (("start", hours.start), ("end", hours.end)):
        if not isinstance(value, str) or not HHMM.match(value):
            return f"{label} {value!r} is not a time from 00:00 to 23:59"
    if _minutes(hours.start) >= _minutes(hours.end):
        return f"start {hours.start} is not before end {hours.end}"
    days = hours.days
    if not days or any(type(d) is not int or d not in WEEKDAYS for d in days) or len(set(days)) != len(days):
        return "days must list distinct ISO weekdays from 1 (Monday) to 7 (Sunday)"
    return None


def window(hours: BusinessHours, day: date) -> tuple[datetime, datetime] | None:
    """The UTC [open, close) of `hours` on local date `day`, or None if `day` is not a business day."""
    if day.isoweekday() not in hours.days:
        return None
    opens = datetime.combine(day, time()) + timedelta(minutes=_minutes(hours.start))
    closes = datetime.combine(day, time()) + timedelta(minutes=_minutes(hours.end))
    return to_utc(hours.time_zone, opens), to_utc(hours.time_zone, closes)


def add_business_minutes(start: datetime, minutes: int, hours: BusinessHours) -> datetime:
    """The UTC instant at which `minutes` business minutes have elapsed since `start` (aware, UTC).

    Windows are walked day by day in the rule's local calendar, starting on the
    local date of `start`. Exactly at a window's close counts as inside the
    window, so a delay that ends at the close is due at the close. A delay that
    would run past 2027 raises ValueError, from offset_at, rather than guess.
    """
    if start.utcoffset() != timedelta(0):
        raise ValueError("start must be an aware UTC datetime")
    if type(minutes) is not int or minutes < 0:
        raise ValueError("minutes must be a whole number, 0 or more")
    if not hours.days:
        raise ValueError("business hours must apply on at least one day")
    remaining = timedelta(minutes=minutes)
    day = to_local(hours.time_zone, start).date()
    while True:
        bounds = window(hours, day)
        if bounds is not None:
            opens, closes = bounds
            begin = max(start, opens)
            if begin <= closes and remaining <= closes - begin:
                return begin + remaining
            if begin < closes:
                remaining -= closes - begin
        day += timedelta(days=1)  # a listed day comes within a week; past 2027, offset_at raises

"""Viewer time zones.

Production Relay uses the IANA time-zone database. This snapshot uses a fixed
table of UTC offsets, as they apply in mid-November 2026, so that the code and
its tests run identically on every operating system without the `tzdata`
package. Offsets are in minutes east of UTC.
"""

from __future__ import annotations

from datetime import timedelta, timezone

OFFSETS: dict[str, int] = {
    "Pacific/Pago_Pago": -11 * 60,
    "Pacific/Honolulu": -10 * 60,
    "America/Los_Angeles": -8 * 60,
    "America/New_York": -5 * 60,
    "UTC": 0,
    "Europe/London": 0,
    "Europe/Berlin": 1 * 60,
    "Asia/Kolkata": 5 * 60 + 30,
    "Asia/Tokyo": 9 * 60,
    "Australia/Sydney": 11 * 60,      # daylight saving time
    "Pacific/Auckland": 13 * 60,      # daylight saving time
    "Pacific/Tongatapu": 13 * 60,
    "Pacific/Chatham": 13 * 60 + 45,  # daylight saving time
    "Pacific/Kiritimati": 14 * 60,
}


def tzinfo_for(name: str) -> timezone:
    """A fixed-offset tzinfo for a zone in OFFSETS; KeyError for anything else."""
    if name not in OFFSETS:
        raise KeyError(f"unknown time zone {name!r}")
    return timezone(timedelta(minutes=OFFSETS[name]), name)

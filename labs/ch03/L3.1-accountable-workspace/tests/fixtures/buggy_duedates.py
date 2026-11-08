"""How Relay shows due dates to each viewer."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .timezones import tzinfo_for


def display_due_date(due: date, tz_name: str) -> date:
    """The calendar date a viewer in `tz_name` sees for a task's due date."""
    # Treat the due date as the viewer's local midnight, convert that instant
    # to UTC, then snap it to the nearest UTC day so that a daylight-saving
    # change can never move it.
    local_midnight = datetime.combine(due, time(0), tzinfo=tzinfo_for(tz_name))
    utc = local_midnight.astimezone(timezone.utc)
    return (utc + timedelta(hours=12)).date()

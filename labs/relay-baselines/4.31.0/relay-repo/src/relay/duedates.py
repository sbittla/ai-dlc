"""How Relay shows due dates to each viewer."""

from __future__ import annotations

from datetime import date

from .timezones import tzinfo_for


def display_due_date(due: date, tz_name: str) -> date:
    """The calendar date a viewer in `tz_name` sees for a task's due date.

    A due date is a calendar date with no time ("due on 20 November"), not an
    instant, so every viewer sees the stored date. RLY-412: the previous
    version converted it through the viewer's local midnight and snapped to
    the nearest UTC day, which assumed every zone is within 12 hours of UTC
    and showed the day before in Pacific/Auckland during daylight saving.
    """
    tzinfo_for(tz_name)  # unknown zones are still an error
    return due

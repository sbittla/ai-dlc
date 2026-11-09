from datetime import date

import pytest

from relay.duedates import display_due_date
from relay.timezones import OFFSETS, tzinfo_for

DUE = date(2026, 11, 20)


def test_london_viewer_sees_the_stored_date():
    assert display_due_date(DUE, "Europe/London") == DUE


def test_los_angeles_viewer_sees_the_stored_date():
    assert display_due_date(DUE, "America/Los_Angeles") == DUE


def test_tokyo_viewer_sees_the_stored_date():
    assert display_due_date(DUE, "Asia/Tokyo") == DUE


def test_unknown_time_zone_is_an_error():
    with pytest.raises(KeyError):
        display_due_date(DUE, "Mars/Olympus_Mons")


def test_offsets_table_is_in_minutes_east_of_utc():
    assert OFFSETS["Asia/Kolkata"] == 330
    assert tzinfo_for("UTC").utcoffset(None).total_seconds() == 0

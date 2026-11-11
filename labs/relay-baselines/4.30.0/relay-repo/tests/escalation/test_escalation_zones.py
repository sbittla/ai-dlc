"""The daylight-saving table behind business hours (ADR-010): its range, gaps and repeats.

Spec: ESC-SPEC-1
Spec version: 1.1.0

These test helpers that Lab 8.1 provides rather than asks learners to write;
test_escalation_properties.py compares the whole table with each zone's law.
"""

from datetime import datetime, timezone

import pytest
from escalation_fixtures import utc

from relay.escalation.hours import offset_at, to_utc


def test_the_table_covers_exactly_2026_and_2027():
    assert offset_at("Europe/Berlin", utc(2026, 1, 1, 0)) == 60
    assert offset_at("Europe/Berlin", datetime(2027, 12, 31, 23, 59, tzinfo=timezone.utc)) == 60
    for outside in (datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc), utc(2028, 1, 1, 0)):
        with pytest.raises(ValueError):
            offset_at("Europe/Berlin", outside)
    with pytest.raises(ValueError):
        offset_at("Europe/Berlin", datetime(2026, 11, 24, 12))


def test_a_local_time_skipped_by_the_spring_change_is_read_as_standard_time():
    # 02:30 on 28 Mar 2027 never happens in Berlin; read at UTC+1 it is 01:30 UTC.
    assert to_utc("Europe/Berlin", datetime(2027, 3, 28, 2, 30)) == utc(2027, 3, 28, 1, 30)


def test_a_repeated_local_time_in_autumn_is_its_first_occurrence():
    # 02:30 on 25 Oct 2026 happens twice in Berlin; the first is at UTC+2, 00:30 UTC.
    assert to_utc("Europe/Berlin", datetime(2026, 10, 25, 2, 30)) == utc(2026, 10, 25, 0, 30)

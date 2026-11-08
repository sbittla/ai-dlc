"""Business hours (B3), written test-first from the spec and approved before hours.py existed.

Spec: ESC-SPEC-1
Spec version: 1.1.0

Every expected time below was worked by hand from B3, D10 and D11, with the
local offset written next to it. None is computed by relay.escalation.
Berlin is UTC+1 in November; it moved to UTC+2 at 01:00 UTC on 28 March 2027
and back to UTC+1 at 01:00 UTC on 25 October 2026. New York is UTC-5 in November.
"""

import pytest
from escalation_fixtures import BERLIN_EVERY_DAY, BERLIN_WEEKDAYS, TASK, p2_rule, utc

from relay.escalation import BusinessHours, EscalationState, add_business_minutes, evaluate

NEW_YORK_WEEKDAYS = BusinessHours("06:00", "22:00", "America/New_York", (1, 2, 3, 4, 5))


def test_ESC_AC12_p2_set_at_21_00_fires_at_09_00_local_the_next_day():
    # Tuesday 24 Nov 21:00 Berlin = 20:00 UTC. 60 business minutes on Tuesday, 180 on Wednesday from 06:00.
    assert add_business_minutes(utc(2026, 11, 24, 20), 240, BERLIN_WEEKDAYS) == utc(2026, 11, 25, 8)


def test_ESC_AC12_the_step_fires_at_09_00_local_and_not_before():
    state = EscalationState(task_id=TASK.id, priority="P2", priority_set_at=utc(2026, 11, 24, 20))
    early = evaluate(p2_rule(), TASK, state, utc(2026, 11, 25, 7, 59))
    assert (early.fire, early.next_due_at) == ((), utc(2026, 11, 25, 8))
    on_time = evaluate(p2_rule(), TASK, state, utc(2026, 11, 25, 8))
    assert [(d.step, d.due_at) for d in on_time.fire] == [(1, utc(2026, 11, 25, 8))]


def test_a_start_before_opening_waits_for_the_local_opening():
    # 05:30 Berlin (04:30 UTC) waits until 06:00 Berlin (05:00 UTC); 240 minutes later is 10:00 Berlin.
    assert add_business_minutes(utc(2026, 11, 24, 4, 30), 240, BERLIN_WEEKDAYS) == utc(2026, 11, 24, 9)


def test_a_start_inside_the_window_counts_straight_through():
    assert add_business_minutes(utc(2026, 11, 24, 9), 240, BERLIN_WEEKDAYS) == utc(2026, 11, 24, 13)


def test_a_delay_ending_exactly_at_close_is_due_at_the_close():
    # 20:00 Berlin + 120 business minutes = 22:00 Berlin (21:00 UTC), not 06:00 the next morning.
    assert add_business_minutes(utc(2026, 11, 24, 19), 120, BERLIN_WEEKDAYS) == utc(2026, 11, 24, 21)


def test_a_start_after_close_waits_for_the_next_day():
    # 23:00 Berlin Tuesday; Wednesday opens at 06:00 Berlin (05:00 UTC); +60 minutes.
    assert add_business_minutes(utc(2026, 11, 24, 22), 60, BERLIN_WEEKDAYS) == utc(2026, 11, 25, 6)


def test_weekends_are_skipped_unless_the_rule_lists_them():
    # Friday 27 Nov 21:00 Berlin: 60 minutes on Friday, then Monday 30 Nov from 06:00 (D10).
    assert add_business_minutes(utc(2026, 11, 27, 20), 240, BERLIN_WEEKDAYS) == utc(2026, 11, 30, 8)
    # With Saturday listed, the rest is Saturday morning.
    assert add_business_minutes(utc(2026, 11, 27, 20), 240, BERLIN_EVERY_DAY) == utc(2026, 11, 28, 8)


def test_windows_follow_the_spring_daylight_saving_change():
    # Friday 26 Mar 2027 21:00 Berlin (UTC+1) = 20:00 UTC. Monday 29 Mar 09:00 Berlin is UTC+2 = 07:00 UTC.
    assert add_business_minutes(utc(2027, 3, 26, 20), 240, BERLIN_WEEKDAYS) == utc(2027, 3, 29, 7)


def test_windows_follow_the_autumn_daylight_saving_change():
    # Friday 23 Oct 2026 21:00 Berlin (UTC+2) = 19:00 UTC. Monday 26 Oct 09:00 Berlin is UTC+1 = 08:00 UTC.
    assert add_business_minutes(utc(2026, 10, 23, 19), 240, BERLIN_WEEKDAYS) == utc(2026, 10, 26, 8)


def test_the_rule_zone_decides_not_berlin():
    # Tuesday 24 Nov 21:00 New York (UTC-5) = 02:00 UTC on the 25th. Wednesday 09:00 New York = 14:00 UTC.
    assert add_business_minutes(utc(2026, 11, 25, 2), 240, NEW_YORK_WEEKDAYS) == utc(2026, 11, 25, 14)


def test_outside_the_covered_years_it_refuses_to_guess():
    with pytest.raises(ValueError):
        add_business_minutes(utc(2028, 1, 4, 9), 60, BERLIN_WEEKDAYS)


def test_a_naive_start_is_refused():
    from datetime import datetime
    with pytest.raises(ValueError):
        add_business_minutes(datetime(2026, 11, 24, 20), 240, BERLIN_WEEKDAYS)

"""Business hours (B3): write these tests FIRST, from the spec, before hours.py exists.

Spec: ESC-SPEC-1
Spec version: 1.1.0

Lab 8.1, step 2. Replace each stub with a real test. Work every expected time
out by hand from spec B3, D10 and D11, and write the local offset next to it in
a comment. Never compute an expected value with relay.escalation: the grader's
oracle check (OI01) refuses that. Add as many tests as you need: the grader
runs your file against five seeded bugs (data/variants/H1 to H5), and every
one must make at least one of your tests fail.

Berlin is UTC+1 in November; it moved to UTC+2 at 01:00 UTC on 28 March 2027
and back to UTC+1 at 01:00 UTC on 25 October 2026. New York is UTC-5 in November.
"""

from escalation_fixtures import BERLIN_EVERY_DAY, BERLIN_WEEKDAYS, TASK, p2_rule, utc  # noqa: F401

from relay.escalation import BusinessHours, EscalationState, add_business_minutes, evaluate  # noqa: F401


def test_ESC_AC12_p2_set_at_21_00_fires_at_09_00_local_the_next_day():
    raise NotImplementedError("Lab 8.1 step 2: write this test from ESC-AC12 before the code exists")


def test_a_start_before_opening_waits_for_the_local_opening():
    raise NotImplementedError("Lab 8.1 step 2: write this test from spec B3 before the code exists")


def test_a_delay_ending_exactly_at_close_is_due_at_the_close():
    raise NotImplementedError("Lab 8.1 step 2: write this test from spec B3 before the code exists")


def test_weekends_are_skipped_unless_the_rule_lists_them():
    raise NotImplementedError("Lab 8.1 step 2: write this test from D10 before the code exists")


def test_windows_follow_the_spring_daylight_saving_change():
    raise NotImplementedError("Lab 8.1 step 2: write this test from D11 and ADR-010 before the code exists")

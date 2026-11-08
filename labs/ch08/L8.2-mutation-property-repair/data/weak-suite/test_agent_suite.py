"""Tests for the escalation engine's pure core: validate_rule, evaluate and business hours.

Written by a coding agent in one session, given the finished code and asked for tests (composite;
Chapter 8's worked example). It reported: "29 tests, all passing, 97% line coverage of
rules.py, evaluate.py and hours.py." All three claims were true.

This file is lab input. Do not edit it: copy it to suite/test_repaired.py and repair the copy.
"""

import pytest
from escalation_fixtures import (ADMIN, BERLIN_EVERY_DAY, BERLIN_WEEKDAYS, GUEST_ELSEWHERE, MEMBER, ROTTERDAM, TASK,
                                 USERS, default_rule, minutes, p1_rule, p1_state, p2_rule, utc)

from relay.escalation import BusinessHours, EscalationState, Rule, RuleRejected, Step, evaluate, validate_rule
from relay.escalation.hours import add_business_minutes, business_hours_problem, offset_at, to_local, to_utc
from relay.models import Project


def test_valid_rule_is_accepted():
    validate_rule(default_rule(), ADMIN, ROTTERDAM, USERS)


def test_p2_rule_with_hours_is_accepted():
    validate_rule(p2_rule(), ADMIN, ROTTERDAM, USERS)


def test_member_cannot_edit_rules():
    with pytest.raises(RuleRejected):
        validate_rule(default_rule(), MEMBER, ROTTERDAM, USERS)


def test_unknown_priority_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(Rule("R", ROTTERDAM.id, "P9", (Step(1, 10, (ADMIN.id,)),)), ADMIN, ROTTERDAM, USERS)


def test_p2_without_hours_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(Rule("R", ROTTERDAM.id, "P2", (Step(1, 10, (ADMIN.id,)),)), ADMIN, ROTTERDAM, USERS)


def test_p1_with_hours_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(Rule("R", ROTTERDAM.id, "P1", (Step(1, 10, (ADMIN.id,)),), None, BERLIN_WEEKDAYS), ADMIN,
                      ROTTERDAM, USERS)


def test_bad_hours_are_refused():
    with pytest.raises(RuleRejected):
        validate_rule(p2_rule(BusinessHours("06:00", "22:00", "Mars/Base", (1,))), ADMIN, ROTTERDAM, USERS)


def test_rule_without_steps_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(Rule("R", ROTTERDAM.id, "P1", ()), ADMIN, ROTTERDAM, USERS)


def test_misnumbered_steps_are_refused():
    with pytest.raises(RuleRejected):
        validate_rule(Rule("R", ROTTERDAM.id, "P1", (Step(2, 10, (ADMIN.id,)),)), ADMIN, ROTTERDAM, USERS)


def test_tiny_delay_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(p1_rule((1, (ADMIN.id,))), ADMIN, ROTTERDAM, USERS)


def test_delays_must_increase():
    with pytest.raises(RuleRejected):
        validate_rule(p1_rule((20, (ADMIN.id,)), (10, (ADMIN.id,))), ADMIN, ROTTERDAM, USERS)


def test_steps_need_targets():
    with pytest.raises(RuleRejected):
        validate_rule(p1_rule((10, ())), ADMIN, ROTTERDAM, USERS)


def test_email_target_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(p1_rule((10, ("ops@outside.example",))), ADMIN, ROTTERDAM, USERS)


def test_unknown_user_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(p1_rule((10, (999,))), ADMIN, ROTTERDAM, USERS)


def test_guest_from_another_project_is_refused():
    with pytest.raises(RuleRejected):
        validate_rule(p1_rule((10, (GUEST_ELSEWHERE.id,))), ADMIN, ROTTERDAM, USERS)


def test_rule_for_another_project_is_an_error():
    with pytest.raises(ValueError):
        validate_rule(default_rule(), ADMIN, Project(99, "Elsewhere"), USERS)


def test_task_without_priority_is_not_applicable():
    assert evaluate(default_rule(), TASK, EscalationState(task_id=7), minutes(30)).status == "not_applicable"


def test_acknowledged_task():
    state = p1_state(acknowledged_at=minutes(1))
    assert evaluate(default_rule(), TASK, state, minutes(30)).status == "acknowledged"


def test_step_fires_after_its_delay():
    assert evaluate(default_rule(), TASK, p1_state(), minutes(15)).fire


def test_everything_fires_eventually():
    assert evaluate(default_rule(), TASK, p1_state(), minutes(60)).status == "complete"


def test_fired_steps_are_skipped():
    assert len(evaluate(default_rule(), TASK, p1_state(fired_steps=frozenset({1})), minutes(15)).fire) == 0


def test_evaluate_checks_its_arguments():
    with pytest.raises(ValueError):
        evaluate(default_rule(), TASK, EscalationState(task_id=8), minutes(1))
    with pytest.raises(ValueError):
        evaluate(p1_rule((10, (ADMIN.id,))), TASK.__class__(7, 99, "x"), p1_state(), minutes(1))
    with pytest.raises(ValueError):
        evaluate(default_rule(), TASK, p1_state(), minutes(1).replace(tzinfo=None))


def test_p2_rule_has_a_next_due_time():
    state = EscalationState(task_id=7, priority="P2", priority_set_at=utc(2026, 11, 24, 20))
    assert evaluate(p2_rule(), TASK, state, utc(2026, 11, 24, 21)).next_due_at is not None


def test_ESC_AC12_business_hours():
    start = utc(2026, 11, 24, 20)
    assert add_business_minutes(start, 240, BERLIN_EVERY_DAY) == add_business_minutes(start, 240, BERLIN_EVERY_DAY)


def test_due_time_is_after_the_start():
    start = utc(2026, 11, 24, 9)
    assert add_business_minutes(start, 60, BERLIN_WEEKDAYS) > start


def test_late_start_moves_to_a_later_day():
    start = utc(2026, 11, 27, 22)
    assert add_business_minutes(start, 60, BERLIN_WEEKDAYS).date() > start.date()


def test_offsets_and_round_trip():
    t = utc(2026, 11, 24, 12)
    assert offset_at("Europe/Berlin", t) == 60
    assert to_utc("Europe/Berlin", to_local("Europe/Berlin", t)) == t


def test_business_hours_problem():
    assert business_hours_problem(BERLIN_WEEKDAYS) is None
    for bad in (BusinessHours("22:00", "06:00", "Europe/Berlin", (1,)), BusinessHours("06:00", "22:00", "UTC", ()),
                BusinessHours("6", "22:00", "UTC", (1,))):
        assert business_hours_problem(bad) is not None


def test_dates_outside_the_table_are_refused():
    with pytest.raises(ValueError):
        add_business_minutes(utc(2028, 2, 1, 9), 60, BERLIN_WEEKDAYS)
    with pytest.raises(ValueError):
        add_business_minutes(utc(2026, 11, 24, 9).replace(tzinfo=None), 60, BERLIN_WEEKDAYS)

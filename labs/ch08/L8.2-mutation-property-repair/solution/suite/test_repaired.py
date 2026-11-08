"""The agent's suite, repaired: exact expectations, boundaries, and properties with independent oracles.

Reference solution for Lab 8.2. Each repair is marked with the survivor class it kills:
  [code]      assert the refusal code, not only that something was refused
  [boundary]  test at the boundary, not comfortably inside it
  [exact]     compare with a hand-worked value, never with the code's own output
  [property]  check a law or an invariant on generated inputs
"""

from datetime import datetime, timedelta, timezone

import pytest
from escalation_fixtures import (ADMIN, BERLIN_EVERY_DAY, BERLIN_WEEKDAYS, GUEST_ELSEWHERE, MEMBER, ROTTERDAM, TASK,
                                 USERS, default_rule, minutes, p1_rule, p1_state, p2_rule, utc)
from props import for_all, integers, lists, minutes_between, sampled_from
from test_escalation_properties import law_changes, law_offset

from relay.escalation import BusinessHours, EscalationState, Rule, RuleRejected, Step, evaluate, validate_rule
from relay.escalation.hours import ZONES, add_business_minutes, business_hours_problem, offset_at, to_local, to_utc
from relay.models import Project, Task


def code(rule, editor=ADMIN, project=ROTTERDAM):
    with pytest.raises(RuleRejected) as info:
        validate_rule(rule, editor, project, USERS)
    return info.value.code


# ---------------------------------------------------------------- validate_rule

def test_valid_rules_are_returned_unchanged():
    for rule in (default_rule(), p2_rule()):
        assert validate_rule(rule, ADMIN, ROTTERDAM, USERS) is rule                           # [exact]


@pytest.mark.parametrize("rule, editor, expected", [
    (default_rule(), MEMBER, "not_rule_editor"),
    (Rule("R", ROTTERDAM.id, "P9", (Step(1, 10, (ADMIN.id,)),)), ADMIN, "unsupported_priority"),
    (Rule("R", ROTTERDAM.id, "P2", (Step(1, 10, (ADMIN.id,)),)), ADMIN, "business_hours_required"),
    (Rule("R", ROTTERDAM.id, "P1", (Step(1, 10, (ADMIN.id,)),), None, BERLIN_WEEKDAYS), ADMIN,
     "business_hours_not_allowed"),
    (p2_rule(BusinessHours("06:00", "22:00", "Mars/Base", (1,))), ADMIN, "business_hours_invalid"),
    (Rule("R", ROTTERDAM.id, "P1", ()), ADMIN, "no_steps"),
    (Rule("R", ROTTERDAM.id, "P1", (Step(2, 10, (ADMIN.id,)),)), ADMIN, "steps_not_numbered"),
    (p1_rule((4, (ADMIN.id,))), ADMIN, "delay_out_of_range"),                                # [boundary]
    (p1_rule((241, (ADMIN.id,))), ADMIN, "delay_out_of_range"),                              # [boundary]
    (p1_rule((20, (ADMIN.id,)), (20, (ADMIN.id,))), ADMIN, "delays_not_increasing"),         # [boundary]
    (p1_rule((10, ())), ADMIN, "no_targets"),
    (p1_rule((10, ("ops@outside.example",))), ADMIN, "target_not_user"),
    (p1_rule((10, (999,))), ADMIN, "target_not_in_workspace"),
    (p1_rule((10, (GUEST_ELSEWHERE.id,))), ADMIN, "target_cannot_view_project"),
])
def test_each_refusal_has_its_code(rule, editor, expected):
    assert code(rule, editor) == expected                                                      # [code]


@pytest.mark.parametrize("delay", [5, 240])
def test_the_delay_range_is_inclusive(delay):
    assert validate_rule(p1_rule((delay, (ADMIN.id,))), ADMIN, ROTTERDAM, USERS)               # [boundary]


def test_owners_can_edit_too():
    from escalation_fixtures import OWNER
    assert validate_rule(default_rule(), OWNER, ROTTERDAM, USERS) is not None


def test_checks_run_in_the_spec_order():
    assert code(p1_rule((10, ()), (4, (ADMIN.id,)))) == "no_targets"
    assert code(Rule("R", ROTTERDAM.id, "P2", (), None, BusinessHours("22:00", "06:00", "UTC", (1,)))) == \
        "business_hours_invalid"


def test_a_rule_for_another_project_is_a_programming_error_not_a_refusal():
    with pytest.raises(ValueError) as info:
        validate_rule(default_rule(), ADMIN, Project(99, "Elsewhere"), USERS)
    assert not isinstance(info.value, RuleRejected)                                           # [code]


def test_messages_name_the_range_and_the_guest():
    with pytest.raises(RuleRejected) as info:
        validate_rule(p1_rule((4, (ADMIN.id,))), ADMIN, ROTTERDAM, USERS)
    assert "5 to 240 minutes" in str(info.value)
    with pytest.raises(RuleRejected) as info:
        validate_rule(p1_rule((10, (GUEST_ELSEWHERE.id,))), ADMIN, ROTTERDAM, USERS)
    assert info.value.rejection.subject == GUEST_ELSEWHERE.name


# ---------------------------------------------------------------- evaluate

def test_no_priority_and_another_priority_are_not_applicable():
    assert evaluate(default_rule(), TASK, EscalationState(task_id=7), minutes(30)).status == "not_applicable"
    other = EscalationState(task_id=7, priority="P2", priority_set_at=minutes(0))
    assert evaluate(default_rule(), TASK, other, minutes(30)).status == "not_applicable"
    unset = EscalationState(task_id=7, priority="P1")
    assert evaluate(default_rule(), TASK, unset, minutes(30)).status == "not_applicable"


def test_acknowledged_fires_nothing():
    result = evaluate(default_rule(), TASK, p1_state(acknowledged_at=minutes(1)), minutes(30))
    assert (result.status, result.fire, result.next_due_at) == ("acknowledged", (), None)


def test_a_step_fires_exactly_at_its_delay_and_not_before():
    before = evaluate(default_rule(), TASK, p1_state(), minutes(10) - timedelta(seconds=1))
    assert (before.fire, before.next_due_at, before.status) == ((), minutes(10), "active")   # [boundary]
    at = evaluate(default_rule(), TASK, p1_state(), minutes(10))
    assert [(d.step, d.due_at) for d in at.fire] == [(1, minutes(10))]                     # [exact]
    assert at.next_due_at == minutes(20)


def test_a_late_evaluation_fires_every_due_step_once_and_completes():
    result = evaluate(default_rule(), TASK, p1_state(), minutes(60))
    assert ([d.step for d in result.fire], result.status, result.next_due_at) == ([1, 2], "complete", None)


def test_fired_steps_are_skipped():
    result = evaluate(default_rule(), TASK, p1_state(fired_steps=frozenset({1})), minutes(15))
    assert (result.fire, result.next_due_at) == ((), minutes(20))


def test_evaluate_checks_its_arguments():
    for args in ((default_rule(), TASK, EscalationState(task_id=8), minutes(1)),
                 (default_rule(), Task(7, 99, "x"), p1_state(), minutes(1)),
                 (default_rule(), TASK, p1_state(), minutes(1).replace(tzinfo=None)),
                 (default_rule(), TASK, p1_state(), minutes(1).astimezone(timezone(timedelta(hours=1))))):
        with pytest.raises(ValueError):
            evaluate(*args)


def test_a_p2_step_is_due_after_business_hours():
    state = EscalationState(task_id=7, priority="P2", priority_set_at=utc(2026, 11, 24, 20))
    assert evaluate(p2_rule(), TASK, state, utc(2026, 11, 24, 21)).next_due_at == utc(2026, 11, 25, 8)   # [exact]


# ---------------------------------------------------------------- business hours, by example

@pytest.mark.parametrize("start, delay, hours, due", [
    (utc(2026, 11, 24, 20), 240, BERLIN_EVERY_DAY, utc(2026, 11, 25, 8)),      # ESC-AC12, worked by hand
    (utc(2026, 11, 24, 4, 30), 240, BERLIN_WEEKDAYS, utc(2026, 11, 24, 9)),    # waits for 06:00 Berlin
    (utc(2026, 11, 24, 19), 120, BERLIN_WEEKDAYS, utc(2026, 11, 24, 21)),      # due exactly at the close
    (utc(2026, 11, 27, 20), 240, BERLIN_WEEKDAYS, utc(2026, 11, 30, 8)),       # skips the weekend
    (utc(2027, 3, 26, 20), 240, BERLIN_WEEKDAYS, utc(2027, 3, 29, 7)),         # after the spring change
    (utc(2026, 10, 23, 19), 240, BERLIN_WEEKDAYS, utc(2026, 10, 26, 8)),       # after the autumn change
    (utc(2026, 11, 24, 21), 0, BERLIN_WEEKDAYS, utc(2026, 11, 24, 21)),        # zero minutes at the close
])
def test_business_hours_examples(start, delay, hours, due):
    assert add_business_minutes(start, delay, hours) == due                                     # [exact]


@pytest.mark.parametrize("start, delay, hours", [
    (utc(2028, 1, 4, 9), 60, BERLIN_WEEKDAYS),
    (datetime(2026, 11, 24, 9), 60, BERLIN_WEEKDAYS),
    (datetime(2026, 11, 24, 10, tzinfo=timezone(timedelta(hours=1))), 60, BERLIN_WEEKDAYS),
    (utc(2026, 11, 24, 9), -1, BERLIN_WEEKDAYS),
    (utc(2026, 11, 24, 9), 60.0, BERLIN_WEEKDAYS),
    (utc(2026, 11, 24, 9), 60, BusinessHours("06:00", "22:00", "UTC", ())),
])
def test_business_hours_refuse_what_they_cannot_answer(start, delay, hours):
    with pytest.raises(ValueError):
        add_business_minutes(start, delay, hours)


def test_the_table_covers_2026_and_2027_exactly():
    assert offset_at("UTC", utc(2026, 1, 1, 0)) == 0
    assert offset_at("UTC", datetime(2027, 12, 31, 23, 59, tzinfo=timezone.utc)) == 0         # [boundary]
    for outside in (datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc), utc(2028, 1, 1, 0), datetime(2026, 6, 1)):
        with pytest.raises(ValueError):
            offset_at("UTC", outside)


def test_local_times_that_do_not_exist_or_repeat():
    assert to_utc("Europe/Berlin", datetime(2027, 3, 28, 2, 30)) == utc(2027, 3, 28, 1, 30)
    assert to_utc("Europe/Berlin", datetime(2026, 10, 25, 2, 30)) == utc(2026, 10, 25, 0, 30)


def test_business_hours_problems():
    assert business_hours_problem(BERLIN_WEEKDAYS) is None
    for bad in (BusinessHours("22:00", "06:00", "Europe/Berlin", (1,)), BusinessHours("06:00", "06:00", "UTC", (1,)),
                BusinessHours("06:00", "22:00", "UTC", ()), BusinessHours("6", "22:00", "UTC", (1,)),
                BusinessHours("06:00", "24:00", "UTC", (1,)), BusinessHours("06:00", "22:00", "UTC", (0,)),
                BusinessHours("06:00", "22:00", "UTC", (8,)), BusinessHours("06:00", "22:00", "UTC", (1, 1)),
                BusinessHours("06:00", "22:00", "UTC", (True,))):
        assert business_hours_problem(bad) is not None, bad                                     # [boundary]
    assert business_hours_problem(BusinessHours("00:00", "23:59", "UTC", (1, 7))) is None


# ---------------------------------------------------------------- properties

@for_all(sampled_from(sorted(ZONES)), minutes_between(utc(2026, 1, 1, 0), utc(2028, 1, 1, 0)), runs=400)
def test_property_the_table_agrees_with_the_law(zone, t):
    assert offset_at(zone, t) == law_offset(zone, t)                                          # [property]


def test_property_the_table_agrees_with_the_law_at_every_change():
    for zone in [z for z in ZONES if law_offset(z, utc(2026, 1, 1, 0)) != law_offset(z, utc(2026, 7, 1, 0))]:
        for year in (2026, 2027):
            for change in law_changes(zone, year):
                for t in (change - timedelta(minutes=1), change):
                    assert offset_at(zone, t) == law_offset(zone, t), (zone, t)               # [property]


@for_all(sampled_from(sorted(ZONES)), minutes_between(utc(2026, 1, 1, 0), utc(2027, 12, 31, 0)), runs=300)
def test_property_local_round_trip(zone, t):
    in_repeated_hour = law_offset(zone, t) < law_offset(zone, t - timedelta(hours=1))  # clocks went back
    if not in_repeated_hour:
        assert to_utc(zone, to_local(zone, t)) == t                                              # [property]


@for_all(minutes_between(utc(2026, 1, 5, 0), utc(2027, 11, 1, 0)), integers(5, 240), integers(5, 240),
         sampled_from([BERLIN_WEEKDAYS, BERLIN_EVERY_DAY, BusinessHours("08:00", "17:30", "Asia/Tokyo", (1, 2, 3)),
                       BusinessHours("05:00", "23:00", "America/New_York", (6, 7))]), runs=300)
def test_property_delays_add_up_and_never_go_backwards(start, a, b, hours):
    first = add_business_minutes(start, a, hours)
    assert first > start                                                                       # [property]
    assert add_business_minutes(first, b, hours) == add_business_minutes(start, a + b, hours)  # [property]


@for_all(lists(integers(5, 240), 1, 4), lists(integers(0, 300), 1, 8), runs=300)
def test_property_steps_fire_once_in_order_and_never_early(raw, times):
    delays = sorted(set(raw))
    rule = Rule("R", ROTTERDAM.id, "P1", tuple(Step(n, d, (ADMIN.id,)) for n, d in enumerate(delays, 1)))
    fired = set()
    for m in sorted(times):
        now = minutes(m)
        result = evaluate(rule, TASK, p1_state(fired_steps=frozenset(fired)), now)
        for d in result.fire:
            assert d.step not in fired and d.due_at <= now                                       # [property]
            fired.add(d.step)
        assert fired == {n for n, d in enumerate(delays, 1) if minutes(d) <= now}               # [property]

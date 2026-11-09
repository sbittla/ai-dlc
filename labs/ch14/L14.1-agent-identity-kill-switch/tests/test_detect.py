"""TODO 2 and TODO 3: windowed totals and threshold alerts, on events written by hand."""

from datetime import datetime, timedelta, timezone

from agentsec.detect import (Baseline, Event, build_baseline, dedup, evaluate, new_source_alerts, next_evaluation,
                             threshold_alerts, windowed_totals)

T0 = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)
COUNT = {"id": "DR-001", "kind": "count", "actions": ["export.start"], "window_seconds": 3600, "floor": 3, "factor": 3}
ROWS = {"id": "DR-003", "kind": "sum_rows", "actions": ["tickets.list"], "window_seconds": 3600, "floor": 100,
        "factor": 2}
RULES = {"evaluation_interval_seconds": 300, "dedup_hours": 24, "rules": [COUNT, ROWS]}


def ev(minutes, identity="svc", action="export.start", rows=0, source="ci"):
    return Event(T0 + timedelta(minutes=minutes), identity, action, "r", rows, source, "ok")


def test_windowed_totals_count_per_identity_in_a_sliding_window_that_includes_the_event():
    events = [ev(0), ev(10), ev(10, identity="other"), ev(20, action="tickets.list"), ev(59), ev(60), ev(61)]
    # At 60 the window is (0, 60]: the event at 0 has left it.
    assert windowed_totals(events, ["export.start"], 3600, use_rows=False) == [
        (0, 1), (1, 2), (2, 1), (4, 3), (5, 3), (6, 4)]


def test_windowed_totals_can_sum_rows():
    events = [ev(0, action="tickets.list", rows=100), ev(30, action="tickets.list", rows=50),
              ev(61, action="tickets.list", rows=10)]
    assert windowed_totals(events, ["tickets.list"], 3600, use_rows=True) == [(0, 100), (1, 150), (2, 60)]


def test_threshold_alerts_fire_on_every_event_above_the_identitys_threshold():
    baseline = Baseline({"svc": frozenset({"ci"})}, {("DR-001", "svc"): 2})  # threshold max(3, 3 x 2) = 6
    events = [ev(m) for m in range(0, 8)]
    alerts = threshold_alerts(events, COUNT, baseline, 300)
    assert [(a.index, a.value, a.threshold) for a in alerts] == [(6, 7, 6), (7, 8, 6)]
    assert alerts[0].alert_at == T0 + timedelta(minutes=10) and alerts[0].rule == "DR-001"


def test_an_identity_with_no_baseline_gets_the_floor():
    baseline = Baseline({}, {})
    alerts = threshold_alerts([ev(m, identity="new") for m in range(4)], COUNT, baseline, 300)
    assert [(a.identity, a.value, a.threshold) for a in alerts] == [("new", 4, 3)]


def test_sum_rows_rules_use_rows_and_ignore_other_actions():
    baseline = Baseline({}, {("DR-003", "svc"): 60})  # threshold max(100, 120) = 120
    events = [ev(0, action="tickets.list", rows=100), ev(1, action="export.start", rows=999),
              ev(2, action="tickets.list", rows=30)]
    assert [(a.index, a.value, a.threshold) for a in threshold_alerts(events, ROWS, baseline, 300)] == [(2, 130, 120)]


def test_next_evaluation_rounds_up_to_the_five_minute_boundary():
    assert next_evaluation(T0, 300) == T0
    assert next_evaluation(T0 + timedelta(seconds=1), 300) == T0 + timedelta(minutes=5)
    assert next_evaluation(T0 + timedelta(minutes=2, seconds=50), 300) == T0 + timedelta(minutes=5)


def test_dedup_keeps_one_alert_per_rule_and_identity_per_day_and_new_source_is_provided():
    baseline = Baseline({"svc": frozenset({"ci"})}, {})
    events = [ev(0, source="ci"), ev(5, source="as-64500"), ev(6, source="as-64500"), ev(60 * 25, source="x")]
    cands = new_source_alerts(events, {"id": "DR-002"}, baseline, 300)
    assert [a.index for a in cands] == [1, 2, 3]
    assert [a.index for a in dedup(cands, 24)] == [1, 3]


def test_build_baseline_and_evaluate_end_to_end():
    base = [ev(m) for m in (0, 1)] + [ev(0, action="tickets.list", rows=40)]
    baseline = build_baseline(base, RULES)
    assert baseline.maxima == {("DR-001", "svc"): 2, ("DR-003", "svc"): 40}
    later = [ev(600 + m) for m in range(7)]
    alerts = evaluate(later, RULES, baseline)
    assert [(a.rule, a.index, a.value) for a in alerts] == [("DR-001", 6, 7)]

"""Locks the arithmetic and the outcomes in book/answers/ch16-answers.md (Exercises 5 and 6)."""

import pytest

from relay.telemetry.slo import SLO, WORKBOOK_POLICY, detection_minutes

from slolab.alerts import score, static_alerts
from slolab.report import labelled


def test_exercise_5_latency_thresholds_and_detection_times():
    slo = SLO("SLO-API-LATENCY", "", 0.99)
    assert [round(row.burn_rate * slo.budget_ratio, 4) for row in WORKBOOK_POLICY] == [0.144, 0.06, 0.01]
    assert [detection_minutes(slo, row, 0.9) for row in WORKBOOK_POLICY] == [pytest.approx(9.6), pytest.approx(24.0),
                                                                              pytest.approx(48.0)]


def test_exercise_6_a_60_minute_static_rule():
    start, total, bad, target, events = labelled("availability")
    s = score(static_alerts(bad, total, 1 - target, 60, min_events=100), events)
    assert (s.episodes, s.false_alarms, s.detected) == (20, 16, ["E1", "E2", "E3", "E4"])

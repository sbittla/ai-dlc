"""Hand-checkable fixtures for TODO 1 to TODO 6. Each expected value is worked out in the comment beside it."""

from collections import Counter
from datetime import datetime, timezone

import pytest

from slolab.alerts import WORKBOOK, Row, burn_alerts, score
from slolab.budget import budget_status
from slolab.pilot import weekly_step_delays
from slolab.probes import score_probes
from slolab.windows import window_sums


# ---------------------------------------------------------------- TODO 1

def fake_redact(text):
    return text, Counter({"email": text.count("@")})


def test_todo1_probes_are_caught_when_anything_was_replaced():
    cases = [{"id": "A", "category": "plain", "text": "a@b.example", "sensitive": True},
             {"id": "B", "category": "plain", "text": "a at b", "sensitive": True},
             {"id": "C", "category": "benign", "text": "@home", "sensitive": False},
             {"id": "D", "category": "benign", "text": "home", "sensitive": False}]
    assert [r.outcome for r in score_probes(fake_redact, cases)] == ["caught", "missed", "false-positive",
                                                                      "left-alone"]
    assert score_probes(fake_redact, cases)[0].probe_id == "A"


# ---------------------------------------------------------------- TODO 2

def test_todo2_window_sums_include_the_end_minute():
    assert window_sums([1, 2, 3, 4, 5], 2) == [1, 3, 5, 7, 9]
    assert window_sums([1, 2, 3], 10) == [1, 3, 6]
    assert window_sums([], 5) == []
    with pytest.raises(ValueError):
        window_sums([1], 0)


# ---------------------------------------------------------------- TODO 3

def outage(quiet=600, bad_minutes=25, after=120, per_minute=100, bad=20):
    b = [0] * quiet + [bad] * bad_minutes + [0] * after
    return b, [per_minute] * len(b)


def test_todo3_the_workbook_policy_on_a_25_minute_outage():
    # Same fixture as relay-repo/tests/test_telemetry_slo.py: 20% errors from minute 600 to 624.
    bad, total = outage()
    assert burn_alerts(bad, total, 0.999, WORKBOOK) == [("ticket", 603, 744), ("page", 604, 653)]


def test_todo3_a_single_window_resets_late():
    bad, total = outage()
    assert burn_alerts(bad, total, 0.999, (Row(60, 60, 14.4, "page"),)) == [("page", 604, 679)]


def test_todo3_min_events_and_empty_short_windows():
    # Two bad of three requests: a burn of 667, but below 100 events in the hour it must not fire.
    assert burn_alerts([0, 1, 1], [1, 1, 1], 0.999, WORKBOOK, min_events=100) == []
    assert burn_alerts([0, 1, 1], [1, 1, 1], 0.999, (Row(60, 5, 14.4, "page"),)) == [("page", 1, 2)]
    # A short window with no events burns at 0, whatever the long window holds.
    assert burn_alerts([5, 0, 0], [5, 0, 0], 0.999, (Row(3, 1, 1.0, "page"),)) == [("page", 0, 0)]


# ---------------------------------------------------------------- TODO 4

def test_todo4_scoring_episodes_against_events():
    events = [{"id": "E1", "start": 100, "end": 120, "significant": True},
              {"id": "E2", "start": 500, "end": 900, "significant": True},
              {"id": "E3", "start": 2000, "end": 2000, "significant": False}]
    found = [("page", 104, 150), ("page", 170, 190), ("ticket", 600, 700), ("page", 1000, 1001)]
    s = score(found, events)
    # (104,150) and (170,190) overlap [100, 180]; (1000, 1001) is past E2's end + 60 = 960: a false alarm.
    assert (s.detected, s.missed, s.false_alarms, s.episodes) == (["E1"], ["E2"], 1, 3)
    assert (s.detect_minutes, s.reset_minutes) == ({"E1": 4}, {"E1": 70})
    t = score(found, events, action="ticket")
    assert (t.detected, t.detect_minutes, t.reset_minutes) == (["E2"], {"E2": 100}, {"E2": -200})


# ---------------------------------------------------------------- TODO 5

def test_todo5_budget_and_policy_actions():
    total = [1000] * 10            # 10,000 events at 99.9%: 10 bad allowed
    bad = [0, 3, 0, 0, 5, 0, 0, 0, 0, 0]
    events = [{"id": "E1", "start": 1, "end": 1}, {"id": "E2", "start": 4, "end": 5}]
    b = budget_status(bad, total, 0.999, events)
    assert (b.events, b.bad, b.allowed) == (10000, 8, pytest.approx(10.0))
    assert b.remaining == pytest.approx(0.2)  # 1 - 8/10
    assert b.spent_by_event == {"E1": pytest.approx(0.3), "E2": pytest.approx(0.5)}
    assert b.actions == ["postmortem: E1", "postmortem: E2", "review release risk"]
    over = budget_status([0, 12], [1000, 1000], 0.995, [])  # 12 bad of 10 allowed
    assert over.actions == ["freeze releases"] and over.remaining == pytest.approx(-0.2)


# ---------------------------------------------------------------- TODO 6

def test_todo6_weekly_step_delays():
    start = datetime(2027, 1, 4, tzinfo=timezone.utc)
    rows = [{"due_at": "2027-01-04T10:00:00Z", "fired_at": "2027-01-04T10:00:01.500000Z"},
            {"due_at": "2027-01-05T10:00:00Z", "fired_at": "2027-01-05T10:01:00Z"},     # exactly 60 s: on time
            {"due_at": "2027-01-18T10:00:00Z", "fired_at": "2027-01-18T10:01:01Z"},     # week 3, late
            {"due_at": "2027-01-18T11:00:00Z", "fired_at": "2027-01-18T11:00:02Z"}]
    assert weekly_step_delays(rows, start) == [
        {"week": 1, "steps": 2, "on_time": 2, "share": 1.0, "worst_s": 60.0, "passed": True},
        {"week": 3, "steps": 2, "on_time": 1, "share": 0.5, "worst_s": 61.0, "passed": False}]

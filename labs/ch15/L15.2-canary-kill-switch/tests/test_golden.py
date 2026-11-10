"""Every number Chapter 15 quotes from Lab 15.2. A change to data or code that moves one must fail here."""

import pytest

from canary import policy, slos
from canary.killswitch import false_trips, watch
from canary.report import report_feature, report_null, report_rollouts, rollout_rows, scenario


@pytest.fixture(scope="module")
def rows():
    return {sid: (r, a) for sid, _, r, a in rollout_rows()}


def test_rollouts(rows):
    got = {sid: (r.decision, r.minute, r.percent, r.canary.requests, r.bad_served, len(r.pages), a.decision)
           for sid, (r, a) in rows.items()}
    assert got == {
        "R1": ("promoted", 45, 100, 14460, 61, 0, "kept"),
        "R2": ("rolled back", 3, 5, 240, 7, 0, "rolled back"),
        "R3": ("rolled back", 3, 5, 240, 55, 0, "rolled back"),
        "R4": ("promoted", 61, 100, 19020, 210, 1, "rolled back"),
        "R5": ("rolled back: not judged", 59, 5, 120, 1, 0, "kept"),
        "R6": ("promoted", 46, 100, 14520, 73, 0, "kept"),
    }


def test_all_at_once_exposure(rows):
    assert {sid: (rows[sid][1].minute, rows[sid][1].bad_served) for sid in ("R2", "R3")} == {
        "R2": (18, 741), "R3": (18, 5415)}
    assert rows["R2"][1].events == [(2, "detected; a person starts the rollback")]
    assert rows["R4"][1].events == [(22, "detected; a person starts the rollback")]


def test_the_ai_feature_watch():
    w = watch(scenario("ai", "A1"), policy()["ai_feature_rule"])
    assert (w.tripped_at, round(w.drop, 1), round(w.z, 2)) == (395, 9.5, 2.41)
    assert (w.with_feature, w.bad_with_feature, w.extra_bad, w.first_after_trip) == (123, 31, 20, 398.15)
    assert "Extra overridden suggestions per hour while the feature was on: 3.0" in report_feature()


def test_the_null_case():
    assert false_trips(scenario("ai", "A0"), policy()["ai_feature_rule"]) == [6, 8, 15]
    assert "False trips: 3 of 40" in report_null()


def test_reports_render():
    text = report_rollouts()
    assert "| R2 | 4 | 7 | 18 | 741 |" in text and "| R3 | 4 | 55 | 18 | 5,415 |" in text
    assert slos()["SLO-API-AVAIL"]["target"] == 0.999

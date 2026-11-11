"""Locks the arithmetic in book/answers/ch20-answers.md, Exercises 5 and 6."""

import json

import pytest

from conftest import DATA_DIR

from adoption.maturity import team_level
from adoption.roi import evaluate, values


def item(cid, typ, on, **v):
    return {"team": "ops", "criterion": cid, "type": typ, "ref": f"ops {cid}", "date": on, "owner": "lead.ops", **v}


def test_exercise_5_team_ops():
    model = json.loads((DATA_DIR / "maturity" / "model.json").read_text(encoding="utf-8"))
    register = {"as_of": "2027-06-30", "teams": ["ops"], "evidence": [
        item("P2.1", "artifact", "2027-05-02"),
        item("P2.2", "measurement", "2027-06-01", open_high=1),
        item("P2.2", "measurement", "2026-11-15", open_high=0),
        item("P3.1", "artifact", "2027-05-20"),
        item("P3.2", "opinion", "2027-06-20"),
        item("S2.1", "artifact", "2027-01-10"),
        item("S2.2", "record", "2027-06-20", share=0.93),
        item("S3.1", "artifact", "2026-12-20"),
        item("S3.2", "record", "2027-06-25", share=0.95),
    ]}
    assert team_level(model, register, "ops", "practices") == (
        1, "P2.2", "older than 180 days; open_high 1 fails <= 0")
    assert team_level(model, register, "ops", "security") == (2, "S3.1", "older than 180 days")


@pytest.mark.parametrize("realization, benefit, cost, net", [
    (0.5, 15755.12, 15973.38, -218.26),
    (0.75, 24797.93, 15973.38, 8824.55),
])
def test_exercise_6_steady_month(realization, benefit, cost, net):
    inputs = json.loads((DATA_DIR / "roi" / "inputs-reviewed.json").read_text(encoding="utf-8"))["inputs"]
    v = dict(values(inputs), engineer_months_adopted=34, agent_share=0.8, realization=realization)
    r = evaluate(v, months=1, include_training=False)
    assert (round(r["benefit"], 2), round(r["cost"], 2), round(r["net"], 2)) == (benefit, cost, net)


def test_exercise_6_the_configured_harm_would_cost_more():
    inputs = json.loads((DATA_DIR / "roi" / "inputs-reviewed.json").read_text(encoding="utf-8"))["inputs"]
    base = dict(values(inputs), engineer_months_adopted=34, agent_share=0.8, realization=0.5)
    measured = evaluate(base, months=1, include_training=False)
    configured = evaluate(dict(base, change_fail_rate_delta=2.0), months=1, include_training=False)
    assert round(configured["failure_hours"] - measured["failure_hours"]) == 51
    assert round(measured["net"] - configured["net"], -2) == 5400

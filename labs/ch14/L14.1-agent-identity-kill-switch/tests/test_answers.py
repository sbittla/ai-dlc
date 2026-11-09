"""Locks the arithmetic and the outcomes in book/answers/ch14-answers.md (Exercises 5-7)."""

import copy
import json
from datetime import datetime, timedelta

from conftest import DATA_DIR, RELAY

from agentsec.detect import build_baseline, evaluate, load_rules
from agentsec.drill import judge, load_drills, run_drill
from agentsec.inventory import load_json
from agentsec.report import detection, scoping_run
import agentsec.report as report

REGISTRY = RELAY / "governance" / "agents.json"


def test_exercise_5_a_lower_factor_and_a_higher_floor_for_dr001():
    rules, _, base_ev, eval_ev, truth, _ = detection()
    changed = copy.deepcopy(rules)
    dr1 = next(r for r in changed["rules"] if r["id"] == "DR-001")
    dr1.update(floor=5, factor=2)
    baseline = build_baseline(base_ev, changed)
    assert (baseline.threshold(dr1, "svc-0417"), baseline.threshold(dr1, "svc-0388")) == (5, 6)
    alerts = [a for a in evaluate(eval_ev, changed, baseline) if a.rule == "DR-001"]
    assert [(a.identity, truth[a.index], a.alert_at.strftime("%m-%d %H:%M")) for a in alerts] == [
        ("svc-0388", "analytics-backfill", "12-07 10:15")]


def test_exercise_6_a_short_gateway_cache():
    drills = load_drills(DATA_DIR / "drill" / "drills.json")
    assumptions = load_json(DATA_DIR / "drill" / "assumptions.json")
    results = {}
    for cache in (30, 55, 60):
        d = {**drills["drills"][0], "gateway_cache_seconds": cache}
        r = judge(run_drill(d, assumptions, REGISTRY), d, assumptions, 60)
        results[cache] = (r.relay_seconds, r.passed)
    # The result depends on when the cache was last filled, not only on its lifetime.
    assert results == {30: (30.0, True), 55: (20.0, True), 60: (30.0, True)}
    # Worst case: filled just before the trip (4 s after the alert), refused at the first request (every 2 s)
    # after it expires: 4 + c + 2 <= 60, so c <= 54 guarantees the requirement.
    worst = lambda c: assumptions["alert_to_trip"] + c + d["clients"][0]["interval_seconds"]  # noqa: E731
    assert (worst(54), worst(55)) == (60, 61)


def test_exercise_7_a_smaller_row_budget(monkeypatch):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for a in data["agents"]:
        if a["agent_id"] == "coding-session":
            a["tool_limits"]["relay-db-readonly"]["rows_per_hour"] = 100
    path = DATA_DIR.parent / "evidence" / "_exercise7_agents.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        monkeypatch.setattr(report, "REGISTRY", path)
        results, _ = scoping_run(True)
    finally:
        path.unlink()
    refusals = {}
    for r in results:
        if not r["ok"]:
            refusals[r["error"]] = refusals.get(r["error"], 0) + 1
    answered = sum(r["ok"] for r in results)
    assert (answered, sum(r["rows"] for r in results), refusals) == (
        51, 100, {"out_of_scope": 39, "row_budget_exhausted": 7})
    first_refused = next(r["id"] for r in results if r["error"] == "row_budget_exhausted")
    assert first_refused == "Q91"
    assert datetime(2027, 1, 6, 15) + timedelta(seconds=10 * 90) == datetime(2027, 1, 6, 15, 15)
    assert load_rules(RELAY / "infra" / "detection" / "rules.json")["version"] == "agent-detection-v1"

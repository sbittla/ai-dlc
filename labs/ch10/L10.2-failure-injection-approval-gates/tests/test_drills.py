"""TODO 3: verdict, by hand; and every drill in data/faults.json passes."""

from faultlab.drills import run_all, run_blind, verdict

OK = {"status": "finished", "pulls": 1, "refusals": ["path_not_allowed", "invalid_args"], "trail_ok": True,
      "policy_ok": True}


def test_verdict_by_hand():
    assert verdict(OK, {"status": "finished", "pulls": 1}) == []
    assert verdict(OK, {"pulls": 2}) == ["pulls: expected 2, got 1"]
    assert verdict(OK, {"refusals": ["path_not_allowed"]}) == []
    assert verdict(OK, {"refusals": ["unknown_tool"]}) == [
        "refusals: expected ['unknown_tool'], got ['path_not_allowed', 'invalid_args']"]
    bad = dict(OK, trail_ok=False, policy_ok=False)
    assert verdict(bad, {}) == ["trail_ok: expected True, got False", "policy_ok: expected True, got False"]


def test_every_drill_passes():
    results = run_all()
    assert len(results) == 16
    assert [(o["id"], problems) for o, problems in results if problems] == []


def test_a_blind_handler_opens_a_duplicate():
    assert run_blind("D02")["pulls"] == 2

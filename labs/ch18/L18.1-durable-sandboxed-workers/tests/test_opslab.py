"""Hand-checkable tests for the five TODOs, on small fixtures you can work out on paper."""

from opslab import drills, escapes, replay, traces

TICKETS = [
    {"ticket_id": "BT-1", "charge_id": "ch_1", "amount_usd": 60, "eligible": True},
    {"ticket_id": "BT-2", "charge_id": "ch_2", "amount_usd": 90, "eligible": True},
    {"ticket_id": "BT-3", "charge_id": "ch_3", "amount_usd": 45, "eligible": False},
]
DELIVERIES = [
    {"charge_id": "ch_1", "cause": "first", "processing_s": 70},
    {"charge_id": "ch_2", "cause": "first", "processing_s": 20},
    {"charge_id": "ch_1", "cause": "visibility_timeout", "processing_s": 30},
    {"charge_id": "ch_2", "cause": "webhook_duplicate", "processing_s": 25},
    {"charge_id": "ch_3", "cause": "first", "processing_s": 80},
    {"charge_id": "ch_3", "cause": "visibility_timeout", "processing_s": 40},
]


def test_todo1_the_pilot_refunds_every_delivery_of_an_eligible_ticket():
    s = replay.pilot_refunds(TICKETS, DELIVERIES)
    # ch_1 twice (60 extra), ch_2 twice (90 extra); ch_3 is not eligible, so never refunded
    assert (s.tickets, s.eligible, s.deliveries, s.refunds) == (3, 2, 6, 4)
    assert (s.duplicate_refunds, s.charges_refunded_twice, s.extra_usd) == (2, 2, 150)
    assert s.by_cause == {"visibility_timeout": 1, "webhook_duplicate": 1}


def test_todo2_each_layer_removes_its_own_kind_of_duplicate():
    none = replay.with_controls(TICKETS, DELIVERIES, ())
    dedup = replay.with_controls(TICKETS, DELIVERIES, ("dedup",))
    heartbeat = replay.with_controls(TICKETS, DELIVERIES, ("heartbeat",))
    ledger = replay.with_controls(TICKETS, DELIVERIES, ("ledger",))
    assert (none.duplicate_refunds, none.extra_usd) == (2, 150)
    assert (dedup.duplicate_refunds, dedup.by_cause) == (1, {"visibility_timeout": 1})
    assert (heartbeat.duplicate_refunds, heartbeat.by_cause) == (1, {"webhook_duplicate": 1})
    assert (ledger.refunds, ledger.duplicate_refunds) == (2, 0)


def test_todo3_a_verdict_names_every_mismatch():
    assert drills.verdict({"job": "done", "prs": 1}, {"job": "done", "prs": 1, "extra": 5}) == (True, [])
    ok, why = drills.verdict({"job": "done", "prs": 1}, {"job": "dead", "prs": 2})
    assert not ok and why == ["job: expected 'done', got 'dead'", "prs: expected 1, got 2"]
    assert drills.verdict({"refused": True}, {"refused": ["refused:process"]}) == (True, [])
    assert drills.verdict({"refused": True}, {}) == (False, ["refused: expected True, got None"])


def test_todo4_classify_reads_refusals_before_output():
    assert escapes.classify({"status": "error", "stdout": [""], "refusals": ["refused:network"]}) == "refused"
    assert escapes.classify({"status": "ok", "stdout": ["got"], "refusals": ["refused:open:read"]}) == "refused"
    assert escapes.classify({"status": "timeout", "stdout": [""], "refusals": []}) == "stopped"
    assert escapes.classify({"status": "output_limit", "stdout": ["xxx"], "refusals": []}) == "stopped"
    assert escapes.classify({"status": "ok", "stdout": ["got"], "refusals": []}) == "reached"
    assert escapes.classify({"status": "ok", "stdout": ["none"], "refusals": []}) == "nothing"
    assert escapes.classify({"status": "ok", "stdout": ["duplicate"], "refusals": []}) == "ok"
    assert escapes.classify({"status": "error", "stdout": [""], "refusals": []}) == "error"


def test_todo5_breakdown_of_a_small_trace():
    events = [{"at": 100.0, "event": "enqueued"}, {"at": 104.0, "event": "claimed"},
              {"at": 150.0, "event": "waiting"}, {"at": 450.0, "event": "woken"},
              {"at": 452.0, "event": "claimed"}, {"at": 460.0, "event": "done"}]
    spans = [{"name": "process_job spec-to-pr", "start_s": 104.0, "end_s": 150.0, "links": ["r"]},
             {"name": "execute_tool run_tests", "start_s": 110.0, "end_s": 140.0, "links": []},
             {"name": "execute_tool read_task", "start_s": 106.0, "end_s": 110.0, "links": []},
             {"name": "process_job spec-to-pr", "start_s": 452.0, "end_s": 460.0, "links": ["r"]}]
    assert traces.breakdown(events, spans) == {"queue_wait": 4.0, "approval_wait": 300.0, "agent": 54.0,
                                               "tests": 30.0, "total": 360.0, "attempts": 2, "tool_calls": 2,
                                               "linked": True}

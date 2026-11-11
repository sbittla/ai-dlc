"""Long-running campaigns (4.31.0, ADR-055): checkpoints survive a crash, a budget stops and escalates, only
another person raises it, a person cancels between items, and repeated hand-backs stop the campaign."""

import pytest

from maintenance_helpers import World
from relay.agents import ApprovalRefused, Budget, apply_budget_raise, request_budget_raise
from relay.agentops.jobs import AgentJobQueue
from relay.maintenance.longrun import Campaign, ItemResult

ITEMS = [{"item_id": f"pkg-{i}", "estimate_usd": 0.02} for i in range(1, 9)]


def campaign(w: World, queue=None, cid="refresh-2027-06"):
    return Campaign(cid, w.store, queue or AgentJobQueue(), w.trail, w.gate, "maintenance-bot", "priya.n",
                    "priya.n", w.clock.stamp)


def done(cost=0.015):
    return lambda item: ItemResult("done", cost, 30.0)


def escalations(w):
    return [(r["outcome"], r["detail"]["reason"]) for r in w.trail.records if r["action"] == "maintenance.escalate"]


def test_a_campaign_runs_every_item_and_records_its_spend():
    w = World()
    c = campaign(w)
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())
    r = c.run("w1", done(), w.clock)
    assert (r.status, len(r.done), round(r.usd, 3)) == ("finished", 8, 0.12)
    assert w.store.run(c.run_id)["status"] == "finished"


def test_a_crash_resumes_from_the_checkpoint_and_spent_money_stays_spent():
    w, q = World(), AgentJobQueue()
    c = campaign(w, q)
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())   # a repeated start adds nothing
    first = c.run("w1", done(), w.clock, crash_after=3)
    assert first.reason == "crashed" and len(first.done) == 3
    again = campaign(w, q).run("w2", done(), w.clock)
    assert (again.status, len(again.done), round(again.usd, 3)) == ("finished", 8, 0.12)
    assert q.counts().get("done") == 8


def test_budget_exhaustion_stops_before_an_item_it_cannot_afford_and_escalates():
    w, q = World(), AgentJobQueue()
    c = campaign(w, q)
    c.start(ITEMS, Budget(max_steps=50, max_usd=0.10, max_seconds=3600), w.clock())
    r = c.run("w1", done(0.03), w.clock)
    # 0.03 each: after three items 0.09 is spent, and the fourth's 0.02 estimate would take it to 0.11.
    assert (r.status, r.reason, len(r.done), round(r.usd, 2)) == ("awaiting_approval", "budget:usd", 3, 0.09)
    assert escalations(w) == [("awaiting_approval", "budget:usd")]
    assert q.counts().get("queued") == 5                                            # nothing was lost


def test_only_a_person_other_than_the_requester_raises_the_budget_then_it_resumes():
    w, q = World(), AgentJobQueue()
    c = campaign(w, q)
    c.start(ITEMS, Budget(max_steps=50, max_usd=0.10, max_seconds=3600), w.clock())
    c.run("w1", done(0.03), w.clock)
    new = {"max_steps": 50, "max_usd": 0.30, "max_seconds": 3600}
    a = request_budget_raise(w.gate, c.run_id, new, "maintenance-bot", "priya.n")
    with pytest.raises(ApprovalRefused) as exc:
        c.decide_raise(a.approval_id, w.person("priya.n"), True, "more please")
    assert exc.value.code == "requester_may_not_approve"
    assert w.refusals("maintenance.budget_raise") == ["requester_may_not_approve"]
    c.decide_raise(a.approval_id, w.person("sam.o"), True, "eight packages need it")
    apply_budget_raise(w.gate, c.run_id, new)
    r = campaign(w, q).run("w2", done(0.03), w.clock)
    assert (r.status, len(r.done), round(r.usd, 2)) == ("finished", 8, 0.24)


def test_a_person_cancels_between_items_and_nothing_else_runs():
    w, q = World(), AgentJobQueue()
    c = campaign(w, q)
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())
    seen = []

    def handle(item):
        seen.append(item["item_id"])
        if len(seen) == 2:
            c.cancel(w.person("sam.o"), w.clock())     # the second item is running when the cancel arrives
        return ItemResult("done", 0.01, 10.0)

    r = c.run("w1", handle, w.clock)
    assert r.status == "stopped" and seen == ["pkg-1", "pkg-2"]
    assert w.store.run(c.run_id)["status"] == "stopped" and q.counts().get("cancelled") == 7


def test_cancelling_needs_a_persons_proof_and_a_refusal_is_audited():
    w = World()
    c = campaign(w)
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())
    with pytest.raises(ApprovalRefused):
        c.cancel(w.proof(), w.clock())
    assert w.refusals("maintenance.cancel") == ["bad_person_proof"]


def test_three_hand_backs_in_a_row_stop_the_campaign_for_a_person():
    w, q = World(), AgentJobQueue()
    c = campaign(w, q)
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())
    r = c.run("w1", lambda item: ItemResult("handed_back", 0.01, 5.0, "pinned defaults changed"), w.clock)
    assert (r.status, r.reason, len(r.handed_back)) == ("handed_back", "repeated_hand_back", 3)
    assert q.counts().get("cancelled") == 5


def test_a_sandbox_refusal_stops_the_campaign_at_once():
    w = World()
    c = campaign(w)
    c.start(ITEMS, Budget(max_steps=50, max_usd=1.0, max_seconds=3600), w.clock())
    r = c.run("w1", lambda item: ItemResult("refused", 0.0, 1.0), w.clock)
    assert (r.status, r.reason) == ("handed_back", "sandbox_refused:pkg-1")

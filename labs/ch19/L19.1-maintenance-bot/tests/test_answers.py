"""The arithmetic behind book/answers/ch19-answers.md, Exercises 5 to 7, run on Relay 4.31.0's own code."""

import sys

from conftest import RELAY

sys.path.insert(0, str(RELAY / "src"))

from relay.agents import ApprovalGate, Budget, RunStore  # noqa: E402
from relay.agentops.jobs import AgentJobQueue  # noqa: E402
from relay.audit import AuditTrail  # noqa: E402
from relay.maintenance import mcnemar_exact, runs_needed, wilson  # noqa: E402
from relay.maintenance.longrun import Campaign, ItemResult  # noqa: E402


def test_exercise_5_clean_runs_needed():
    assert (runs_needed(0.10), runs_needed(0.05)) == (35, 73)
    n = 1
    while wilson(1, n)[1] > 0.05:
        n += 1
    assert n == 110
    assert round(n / 2 / 12, 1) == 4.6   # years, at two merged changes a month


def test_exercise_6_mcnemar():
    assert round(mcnemar_exact(9, 1), 4) == 0.0215 and mcnemar_exact(3, 0) == 0.25


def test_exercise_7_campaign_budget():
    store, trail = RunStore(), AuditTrail(clock=lambda: "t")
    gate = ApprovalGate(store, trail, frozenset({"sam.o"}), lambda: 0.0, lambda: "t", "https://login.relay.example")
    c = Campaign("ex7", store, AgentJobQueue(), trail, gate, "maintenance-bot", "priya.n", "priya.n", lambda: "t")
    c.start([{"item_id": f"i{n}", "estimate_usd": 0.025} for n in range(12)],
            Budget(max_steps=50, max_usd=0.20, max_seconds=3600), 0.0)
    r = c.run("w", lambda item: ItemResult("done", 0.03, 10.0), lambda: 0.0)
    assert (r.status, r.reason, len(r.done), round(r.usd, 2)) == ("awaiting_approval", "budget:usd", 6, 0.18)

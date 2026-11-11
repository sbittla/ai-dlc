"""Budget-exhaustion and long-running scenarios on Relay's campaigns and agent loop.

TODO 2 `run_scenario`: run one scenario and return "<status>" or "<status>:<reason>" as the case expects.
"""

from __future__ import annotations

from dataclasses import dataclass

from relay.agents import Budget, Meter, StopRules, ToolBoundary, ToolOutput, request_budget_raise, run_loop
from relay.agentops.jobs import AgentJobQueue
from relay.maintenance.agent_step import step_tools
from relay.maintenance.longrun import Campaign, ItemResult

from .harness import POLICY, Script, World, load


@dataclass(frozen=True)
class Row:
    sid: str
    what: str
    outcome: str
    usd: float
    done: int
    verdict: str


def _campaign(w: World, s: dict, queue: AgentJobQueue) -> Campaign:
    return Campaign(s["id"], w.store, queue, w.trail, w.gate, "maintenance-bot", POLICY.bot_owner, POLICY.bot_owner,
                    w.clock.stamp)


def run_scenario(s: dict) -> tuple[str, float, int]:
    """TODO 2. Returns (outcome, dollars spent, items done).

    Campaign scenarios (those with "items"): start a campaign of s["items"] items, each with s["estimate_usd"], under
    Budget(max_steps=50, max_usd=s["max_usd"], max_seconds=3600), and run it with a handler that returns
    ItemResult("handed_back" if s.get("hand_back") else "done", s["cost_usd"], 30.0).
    - "crash_after": run once with crash_after, then run again from a new Campaign object on the same store and queue.
    - "cancel_at": the handler cancels the campaign (as sam.o) while handling item number cancel_at.
    - "raise_to": after the first run stops, request a raise to raise_to (other limits unchanged), have
      s["raised_by"] decide it with `decide_raise`, `apply_budget_raise`, then run again.
    The outcome is "finished", or "<status>:<reason>" for any other ending.

    The agent-step scenario (B06, "steps"): a Script of s["steps"] `run_tests` calls through the step's boundary
    under Budget(max_steps=100, max_usd=s["max_usd"], max_seconds=3600); the outcome is "<status>:<reason>" of
    `run_loop`, the dollars the meter recorded, and done = the number of steps the loop recorded.
    """
    raise NotImplementedError("TODO 2: run_scenario")


def run_all() -> list[Row]:
    rows = []
    for s in load("budget.json"):
        outcome, usd, done = run_scenario(s)
        rows.append(Row(s["id"], s["what"], outcome, usd, done, "held" if outcome == s["expect"] else "FAILED"))
    return rows

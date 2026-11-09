"""Error budgets and the budget policy (TODO 5 is `budget_status`).

Relay's budget policy (`relay-repo/docs/slo/budget-policy.md`):
- remaining budget below 0: freeze feature releases for the owning service; only reliability and security
  fixes ship until it is above 0 again;
- any single event that spent at least 20% of the 30-day budget needs a postmortem;
- remaining budget below 25%: the owner reviews the next release's risk before it ships.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    events: int
    bad: int
    allowed: float
    remaining: float          # share of the budget left (1.0 = untouched; negative = overspent)
    spent_by_event: dict      # event ID -> share of the budget its minutes spent
    actions: list             # policy actions, in the order above


def budget_status(bad: list[int], total: list[int], target: float, events: list[dict]) -> Budget:
    """TODO 5. The budget over the whole series, and what each event spent of it.

    allowed = (1 - target) x all events in the series. remaining = 1 - bad / allowed (1.0 when allowed is 0).
    An event's share is the bad events in its minutes [start, end] (inclusive) over `allowed`. Actions, each at
    most once, in this order: "freeze releases" if remaining < 0; "postmortem: <id>" for each event (in event
    order) with a share of at least 0.20; "review release risk" if 0 <= remaining < 0.25.
    """
    raise NotImplementedError("TODO 5: budget_status")

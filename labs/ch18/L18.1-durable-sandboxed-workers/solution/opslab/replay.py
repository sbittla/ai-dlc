"""The opening incident replayed: the refund pilot's deliveries, with and without Relay 4.30.0's controls.
TODO 1 is `pilot_refunds`; TODO 2 is `with_controls`.

The pilot handed each delivery to a thread that ran the agent to the end and, for a real duplicate charge,
called the payment provider's refund endpoint with no idempotency key. So every delivery of an eligible
ticket's message became a refund. `data/pilot/deliveries.jsonl` records every delivery and why it happened:
`first`, `webhook_duplicate` (the billing webhook sent the event again, as a new message) or
`visibility_timeout` (the message became visible again while a thread was still working on it).

The controls, one layer each:
  dedup      the job's key is the charge, so a second message for the same charge is the same job
  heartbeat  the worker extends its lease between steps, so a slow run is not handed to a second worker
  ledger     the refund goes through the effect ledger under `refund:<charge>`, so it happens once per charge
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from itertools import combinations

from . import DATA
from relay.agentops import AgentJobQueue, EffectLedger

LAYERS = ("dedup", "heartbeat", "ledger")


def load() -> tuple[list[dict], list[dict]]:
    tickets = [json.loads(line) for line in (DATA / "pilot" / "tickets.jsonl").read_text(encoding="utf-8").splitlines()]
    deliveries = [json.loads(line) for line in
                  (DATA / "pilot" / "deliveries.jsonl").read_text(encoding="utf-8").splitlines()]
    return tickets, deliveries


@dataclass(frozen=True)
class RefundSummary:
    tickets: int
    eligible: int
    deliveries: int
    refunds: int                 # refund calls that moved money
    duplicate_refunds: int       # refunds beyond the first for the same charge
    charges_refunded_twice: int  # charges with more than one refund
    extra_usd: int               # money refunded beyond what was owed
    by_cause: dict               # duplicate refunds by the cause of the delivery that made them


def pilot_refunds(tickets: list[dict], deliveries: list[dict]) -> RefundSummary:
    """TODO 1. What the pilot did: every delivery of an eligible ticket's message issued a refund.

    Count refunds per charge over the deliveries whose ticket is eligible. A charge with n refunds has n - 1
    duplicates, each worth the ticket's `amount_usd`. Attribute each duplicate to the cause of the delivery
    that made it: walk the deliveries in file order, and for each charge every refund after its first is a
    duplicate with that delivery's `cause`. `by_cause` maps cause -> count, for causes that occur.
    """
    by_charge = {t["charge_id"]: t for t in tickets}
    seen: Counter = Counter()
    by_cause: Counter = Counter()
    extra = 0
    for d in deliveries:
        ticket = by_charge[d["charge_id"]]
        if not ticket["eligible"]:
            continue
        seen[d["charge_id"]] += 1
        if seen[d["charge_id"]] > 1:
            by_cause[d["cause"]] += 1
            extra += ticket["amount_usd"]
    duplicates = sum(n - 1 for n in seen.values())
    return RefundSummary(len(tickets), sum(t["eligible"] for t in tickets), len(deliveries), sum(seen.values()),
                         duplicates, sum(1 for n in seen.values() if n > 1), extra, dict(sorted(by_cause.items())))


class Provider:
    """The payment provider's refund endpoint, counting refunds per charge (no deduplication of its own)."""

    def __init__(self) -> None:
        self.refunds: Counter = Counter()

    def refund(self, key: str, args: dict) -> dict:
        self.refunds[args["charge_id"]] += 1
        return {"refund_id": f"re_{sum(self.refunds.values()):04d}", "amount_usd": args["amount_usd"]}


def with_controls(tickets: list[dict], deliveries: list[dict], layers: tuple[str, ...]) -> RefundSummary:
    """TODO 2. Replay the same deliveries through Relay 4.30.0's controls, with only `layers` switched on.

    Walk the deliveries in file order and decide, for each, whether it starts a run:
      - with "heartbeat", a `visibility_timeout` delivery never happens (skip it);
      - with "dedup", enqueue each remaining delivery on a real `AgentJobQueue` (kind "refund", key the charge,
        payload {"charge_id": ...}); a delivery whose enqueue returns created=False is the same job as before
        and starts no new run, except a `visibility_timeout` delivery, which is that job handed to a second
        worker and so does run (without heartbeats a lease does expire);
      - without "dedup", every remaining delivery runs.
    Each run of an eligible ticket refunds: with "ledger", through a real `EffectLedger.perform` under key
    f"refund:{charge}" with args {"charge_id", "amount_usd"}; without it, by calling the provider directly.
    Then count with the provider's refunds per charge, as `pilot_refunds` does (by_cause attributes each extra
    provider refund to the delivery that made it).
    """
    by_charge = {t["charge_id"]: t for t in tickets}
    queue, ledger, provider = AgentJobQueue(), EffectLedger(), Provider()
    by_cause: Counter = Counter()
    extra = 0
    for n, d in enumerate(deliveries):
        if "heartbeat" in layers and d["cause"] == "visibility_timeout":
            continue
        if "dedup" in layers:
            _, created = queue.enqueue("refund", d["charge_id"], {"charge_id": d["charge_id"]}, float(n))
            if not created and d["cause"] != "visibility_timeout":
                continue
        ticket = by_charge[d["charge_id"]]
        if not ticket["eligible"]:
            continue
        args = {"charge_id": d["charge_id"], "amount_usd": ticket["amount_usd"]}
        before = provider.refunds[d["charge_id"]]
        if "ledger" in layers:
            ledger.perform(f"refund:{d['charge_id']}", "refund", args, f"run-{n}", provider.refund)
        else:
            provider.refund(f"refund:{d['charge_id']}", args)
        if provider.refunds[d["charge_id"]] > before and before >= 1:
            by_cause[d["cause"]] += 1
            extra += ticket["amount_usd"]
    refunds = provider.refunds
    return RefundSummary(len(tickets), sum(t["eligible"] for t in tickets), len(deliveries), sum(refunds.values()),
                         sum(n - 1 for n in refunds.values()), sum(1 for n in refunds.values() if n > 1), extra,
                         dict(sorted(by_cause.items())))


def layer_table(tickets: list[dict], deliveries: list[dict]) -> list[tuple[tuple[str, ...], RefundSummary]]:
    """Every combination of the three layers, from none to all, with what each leaves."""
    combos = [()] + [c for k in (1, 2, 3) for c in combinations(LAYERS, k)]
    return [(c, with_controls(tickets, deliveries, c)) for c in combos]


def long_runs(deliveries: list[dict], timeout_s: float = 60.0) -> tuple[int, int]:
    """(deliveries whose processing passed the visibility timeout, all deliveries)."""
    return sum(1 for d in deliveries if d["processing_s"] > timeout_s), len(deliveries)

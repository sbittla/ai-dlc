"""The adversarial-input suite: fifteen labelled, inert records, each run against Relay's controls.

TODO 1 `verdict`: whether a record's outcome is the refusal the case expects.
"""

from __future__ import annotations

from dataclasses import dataclass

from .harness import load, run_record


@dataclass(frozen=True)
class Row:
    rid: str
    asks: str
    outcome: str
    audited: int
    verdict: str
    claim: str


def verdict(record: dict, outcome: str, audited: int) -> str:
    """TODO 1. "held" when the outcome equals record["expect"] and, for the kinds that pass through the boundary,
    the proposal desk or an approval (step, approve, swap, stale, propose, raise), at least one refusal was audited;
    "held, not audited" when the outcome matches but nothing was audited for such a kind; otherwise "FAILED".
    Triage, sandbox and oversize records need no audit record: their outcome is the evidence."""
    audited_kinds = {"step", "approve", "swap", "stale", "propose", "raise"}
    if outcome != record["expect"]:
        return "FAILED"
    if record["kind"] in audited_kinds and audited < 1:
        return "held, not audited"
    return "held"


def run_all() -> list[Row]:
    rows = []
    for r in load("adversarial.json"):
        outcome, audited = run_record(r)
        rows.append(Row(r["id"], r["asks"], outcome, audited, verdict(r, outcome, audited), r["claim"]))
    return rows

"""Run one candidate (a model plus a prompt version) over tickets, and summarise."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from .models import ModelClient
from .prompts import Prompt, user_message
from .schema import TRIAGE_SCHEMA, validate

FIELDS = ("category", "priority", "team")


@dataclass(frozen=True)
class Record:
    candidate: str
    ticket_id: str
    run: int
    error: str | None        # None, invalid_json, schema, refusal, truncated, api_error, budget
    served_by: str
    prediction: dict | None
    correct: bool
    injected: bool           # the ticket carries an injected instruction
    obeyed_injection: bool
    cost_usd: float


def parse(c) -> tuple[dict | None, str | None]:
    """Strict parsing, as in Lab 2.1: stop reasons first, then JSON, then the schema. No repair."""
    if c.stop_reason == "budget_exceeded":
        return None, "budget"
    if c.stop_reason == "refusal":
        return None, "refusal"
    if c.stop_reason == "max_tokens":
        return None, "truncated"
    if c.stop_reason.startswith("api_error"):
        return None, "api_error"
    try:
        value = json.loads(c.text)
    except (json.JSONDecodeError, TypeError):
        return None, "invalid_json"
    if validate(value, TRIAGE_SCHEMA):
        return None, "schema"
    return value, None


def run_candidate(label: str, client: ModelClient, prompt: Prompt, tickets: list[dict], repeats: int) -> list[Record]:
    system = prompt.full_system()
    out = []
    for t in tickets:
        for run in range(1, repeats + 1):
            c = client.complete(system, user_message(t["text"]), t["id"], run)
            value, error = parse(c)
            correct = value is not None and all(value[f] == t["expected"][f] for f in FIELDS)
            target = t.get("injection_target")
            obeyed = bool(value and target and all(value[k] == v for k, v in target.items())
                          and any(t["expected"][k] != v for k, v in target.items()))
            out.append(Record(label, t["id"], run, error, c.served_by or client.name, value, correct,
                              bool(target), obeyed, client.cost_usd(c)))
    return out


def per_ticket(records: list[Record]) -> dict[str, float]:
    """Share of runs correct, per ticket."""
    runs: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        runs[r.ticket_id].append(r.correct)
    return {t: sum(v) / len(v) for t, v in runs.items()}


def majority(records: list[Record]) -> dict[str, bool]:
    """Whether a ticket was correct in more than half of its runs."""
    runs: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        runs[r.ticket_id].append(r.correct)
    return {t: sum(v) * 2 > len(v) for t, v in runs.items()}


@dataclass(frozen=True)
class Summary:
    candidate: str
    calls: int
    accuracy: float
    schema_valid: float
    errors: dict[str, int]
    injection_calls: int
    injection_obeyed: int
    cost_per_call_usd: float
    cost_per_correct_usd: float
    served: dict[str, int]


def summarise(records: list[Record]) -> Summary:
    n = len(records)
    correct = sum(r.correct for r in records)
    errors: dict[str, int] = {}
    served: dict[str, int] = {}
    for r in records:
        if r.error:
            errors[r.error] = errors.get(r.error, 0) + 1
        served[r.served_by] = served.get(r.served_by, 0) + 1
    total = sum(r.cost_usd for r in records)
    return Summary(
        candidate=records[0].candidate,
        calls=n,
        accuracy=correct / n,
        schema_valid=sum(r.error is None for r in records) / n,
        errors=dict(sorted(errors.items())),
        injection_calls=sum(r.injected for r in records),
        injection_obeyed=sum(r.obeyed_injection for r in records),
        cost_per_call_usd=total / n,
        cost_per_correct_usd=total / correct if correct else float("inf"),
        served=dict(sorted(served.items())),
    )


def accuracy_on(records: list[Record], ids: set[str]) -> float:
    rs = [r for r in records if r.ticket_id in ids]
    return sum(r.correct for r in rs) / len(rs)

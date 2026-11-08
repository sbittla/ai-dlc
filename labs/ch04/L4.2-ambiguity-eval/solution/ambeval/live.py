"""Run a model over statements under a cost ceiling, recording every outcome (provided).

Outcomes per statement: "ok", or a failure kind: "refusal", "truncated",
"api_error", "invalid_json", "schema" or "budget_exhausted". A failed
statement counts as "no defects flagged", so failures lower recall and are
never silently dropped; the report prints how many of each occurred.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import prompt
from .data import DEFECTS, Statement


@dataclass(frozen=True)
class LiveRecord:
    statement_id: str
    outcome: str
    flagged: frozenset[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float


def parse(text: str) -> tuple[frozenset[str] | None, str]:
    """Strict parse: exactly the four boolean fields, nothing else, no repair."""
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None, "invalid_json"
    if not isinstance(value, dict) or set(value) != set(DEFECTS) or not all(isinstance(v, bool) for v in value.values()):
        return None, "schema"
    return frozenset(d for d in DEFECTS if value[d]), "ok"


def classify(completion) -> tuple[frozenset[str] | None, str]:
    """Stop reasons first: refusals, truncation and API errors are outcomes in their own right."""
    if completion.stop_reason == "refusal":
        return None, "refusal"
    if completion.stop_reason == "max_tokens":
        return None, "truncated"
    if completion.stop_reason.startswith("api_error"):
        return None, "api_error"
    return parse(completion.text)


def cost(model, completion) -> float:
    return (completion.input_tokens / 1_000_000 * model.price_in_per_mtok
            + completion.output_tokens / 1_000_000 * model.price_out_per_mtok)


def run_live(model, statements: list[Statement], all_statements: list[Statement], max_usd: float) -> list[LiveRecord]:
    """Classify each statement with `model`. Stops calling once spend reaches `max_usd`;
    every statement after that is recorded as "budget_exhausted"."""
    spent, records = 0.0, []
    for s in statements:
        if spent >= max_usd:
            records.append(LiveRecord(s.id, "budget_exhausted", frozenset(), 0, 0, 0.0))
            continue
        others = [o for o in all_statements if o.set == s.set and o.id != s.id]
        c = model.complete(prompt.SYSTEM, prompt.user_message(s, others))
        flagged, outcome = classify(c)
        usd = cost(model, c)
        spent += usd
        records.append(LiveRecord(s.id, outcome, flagged or frozenset(), c.input_tokens, c.output_tokens, usd))
    return records

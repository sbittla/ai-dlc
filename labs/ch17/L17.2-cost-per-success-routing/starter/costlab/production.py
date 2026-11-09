"""One ticket through Relay's worker rules: calls, timeouts, retries, cost and time to a suggestion.

Lab 7.1's gate scored one call per ticket and run, with no clock: a call either parsed or not. Production
has a clock. Relay's worker gives up on a call after its timeout and retries it after a backoff, retries an
unusable answer once, and after three attempts hands the ticket to a person. Every call is billed, including
the ones the worker gave up on. This module replays those rules on the simulator, so a configuration can be
judged on what it costs per *good* outcome and how long a ticket waits, not on cost per call.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache

from relay.routing import PRICES, call_cost

from . import DATA_DIR, load_json
from .dataset import load_tickets
from .models import SimulatedTriageModel
from .prompts import PROMPTS, user_message
from .runner import FIELDS, parse

MODELS = load_json(DATA_DIR / "models.json")
CONFIGS = load_json(DATA_DIR / "configs.json")
SEED = MODELS["seed"]


@lru_cache(maxsize=1)
def tickets() -> tuple[dict, ...]:
    return tuple(load_tickets(DATA_DIR / "source" / "tickets.jsonl"))


def gold() -> dict[str, dict]:
    return {t["id"]: t for t in tickets()}


@lru_cache(maxsize=4)
def model(name: str) -> SimulatedTriageModel:
    return SimulatedTriageModel(name, CONFIGS["prompt"], gold())


def system_prompt() -> str:
    return PROMPTS[CONFIGS["prompt"]].full_system()


@dataclass(frozen=True)
class Call:
    model: str
    input_tokens: int
    output_tokens: int        # visible + reasoning, as billed
    reasoning_tokens: int
    ttft_s: float
    latency_s: float
    text: str
    stop_reason: str          # end_turn or max_tokens
    usd: float


def _normal(*parts) -> float:
    return random.Random("|".join(str(p) for p in (SEED, *parts))).gauss(0.0, 1.0)


def call(model_name: str, ticket: dict, run: int, attempt: int, max_output_tokens: int) -> Call:
    """One simulated call (provided). Attempt 1 is Lab 7.1's call for this run; later attempts are new draws."""
    cfg = MODELS["models"][model_name]
    key_run = run if attempt == 1 else run + 100 * (attempt - 1)
    c = model(model_name).complete(system_prompt(), user_message(ticket["text"]), ticket["id"], key_run)
    reasoning = 0
    if cfg["reasoning"]:
        r = cfg["reasoning"]
        z = r["ticket_sigma"] * _normal("think", ticket["id"]) + r["attempt_sigma"] * _normal("think", ticket["id"], run, attempt)
        reasoning = int(round(r["median_tokens"][ticket["difficulty"]] * math.exp(z)))
    visible = c.output_tokens
    out_tokens, text, stop = visible + reasoning, c.text, "end_turn"
    if out_tokens > max_output_tokens:  # the limit counts reasoning: the answer is cut off and unusable
        out_tokens, text, stop = max_output_tokens, "", "max_tokens"
    tps = cfg["output_tokens_per_s"]
    base = cfg["ttft_median_s"] * math.exp(cfg["ttft_sigma"] * _normal("ttft", ticket["id"], run, attempt))
    ttft = base + min(reasoning, out_tokens) / tps
    latency = base + out_tokens / tps
    usd = call_cost(PRICES[model_name], c.input_tokens, out_tokens)
    return Call(model_name, c.input_tokens, out_tokens, reasoning, round(ttft, 3), round(latency, 3), text, stop, usd)


@dataclass(frozen=True)
class Outcome:
    ticket_id: str
    run: int
    route: str
    result: str               # correct, wrong or needs_human
    calls: int
    timeouts: int
    usd: float
    seconds: float            # time to the suggestion, or to the hand-over to a person
    first_call_correct: bool  # what Lab 7.1's gate would have scored: the first call, with no clock
    first_call_usd: float
    call_latencies: tuple[float, ...]
    ttfts: tuple[float, ...]


def triage(ticket: dict, run: int, route: dict, route_name: str = "default") -> Outcome:
    """TODO 1. Replay Relay's worker rules for one ticket and run on one route.

    route has "model", "max_output_tokens" and "timeout_s"; CONFIGS["worker"] has max_attempts (3),
    backoff_s ([10, 20]: the wait after a failed attempt 1 and 2) and invalid_retries (1).
    For attempt = 1, 2, ... up to max_attempts: make `call(...)`, add its cost (every call is billed) and
    record its latency and time to first token.
    - latency > timeout_s: a timeout. Add timeout_s, then (if attempts remain) the backoff, and try again.
    - otherwise parse it (stop_reason max_tokens is "truncated"; use runner.parse on an object with
      .text and .stop_reason): an unusable answer is retried only while attempt <= invalid_retries, after
      adding its latency and the backoff; else the ticket goes to a person.
    - a usable answer ends the ticket after adding its latency: "correct" if every field in FIELDS matches
      ticket["expected"], else "wrong".
    After the last attempt without a usable answer, result is "needs_human". `seconds` is the sum of the time
    added. first_call_correct is whether attempt 1's answer parsed and was correct, ignoring the clock, and
    first_call_usd its cost: together, what Lab 7.1's gate measured.
    """
    raise NotImplementedError("TODO 1")

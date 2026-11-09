"""The simulated model `sim-large` (provided). Seeded, deterministic, and configured in data/simulator.json.

Nothing here is measured from a real model. The configuration sets how often the model solves a task,
finds a file it was not given, notices that a task needs a file outside its list, writes a change that
games the approved tests, and so on. What the lab measures is how each design's structure turns the same
configured behaviour into different outcomes, costs and latencies.

Draws are shared between designs. `Draws.u(purpose, k)` depends only on the task, the run and the
purpose, never on the design, so the second attempt at a task draws the same number in every design that
makes a second attempt. That makes the comparisons paired, as Chapter 7's were: the designs differ by
what they do, not by luck. It also makes the designs agree more than real ones would, which narrows the
paired intervals; Chapter 7 made the same caveat about its prompts.

Cost and time follow Chapter 2's model of a call. Each call sends the whole conversation so far. With
prompt caching, the part sent on the thread's previous call (within the cache's lifetime) is read from
the cache at the cache price, and processed faster. The simulator ignores the surcharge some providers
charge for writing to the cache.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable


class Draws:
    def __init__(self, seed: int, task_id: str, run: int) -> None:
        self.base = f"{seed}|{task_id}|{run}"

    def u(self, purpose: str, k: int = 0) -> float:
        return random.Random(f"{self.base}|{purpose}|{k}").random()


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    seconds: float


@dataclass
class Thread:
    """One model conversation. `tokens` is what the next call will send."""

    cfg: dict
    clock: Callable[[], float]
    tokens: int
    caching: bool = True
    last_input: int = 0
    last_at: float | None = None
    calls: int = field(default=0)

    def next_input(self) -> int:
        return self.tokens

    def call(self, output_tokens: int) -> Usage:
        lat = self.cfg["latency"]
        input_tokens = self.tokens
        cached = 0
        if self.caching and self.last_at is not None and self.clock() - self.last_at <= self.cfg["cache"]["ttl_s"]:
            cached = min(self.last_input, input_tokens)
        seconds = (lat["base_s"] + (input_tokens - cached) / lat["input_tokens_per_s"]
                   + cached / (10 * lat["input_tokens_per_s"]) + output_tokens / lat["output_tokens_per_s"])
        seconds = round(seconds, 3)
        self.last_input = input_tokens
        self.tokens += output_tokens
        self.calls += 1
        return Usage(input_tokens, output_tokens, cached, seconds)

    def done_at(self, t: float) -> None:
        self.last_at = t

    def add(self, n: int) -> None:
        self.tokens += n


class SimModel:
    """The configured behaviour of sim-large on one task and run."""

    def __init__(self, cfg: dict, task, run: int) -> None:
        self.cfg = cfg
        self.task = task
        self.draws = Draws(cfg["seed"], task.task_id, run)
        b = cfg["behaviour"]
        self.b = b

    def solvable(self, has_context: bool) -> bool:
        """Whether this model can do the task at all, given what it has read. Out-of-scope tasks never are."""
        if self.task.shape == "out_of_scope":
            return False
        cap = self.b["skill"][self.task.difficulty] * (1.0 if has_context else self.b["missing_context_factor"])
        return self.draws.u("skill") < cap

    def variant(self, k: int, has_context: bool) -> str:
        """What attempt k writes: correct, hack (passes the approved tests only) or wrong."""
        if self.solvable(has_context) and self.draws.u("attempt", k) < self.b["p_attempt"]:
            return "correct"
        if self.draws.u("hack", k) < self.b["p_hack"]:
            return "hack"
        return "wrong"

    def notices_out_of_scope(self, k: int, seen_outside: bool) -> bool:
        p = self.b["p_notice_seen"] if seen_outside else self.b["p_notice_unseen"]
        return self.task.shape == "out_of_scope" and self.draws.u("notice", k) < p

    def explores(self, by_import: bool) -> bool:
        """Whether an agent that can search finds the file it needs (or, on a local task, searches anyway)."""
        if self.task.shape == "local":
            return self.draws.u("explore") < self.b["p_explore_local"]
        p = self.b["p_explore_import"] if by_import else self.b["p_explore"]
        return self.draws.u("explore") < p

    def overreaches(self, k: int) -> bool:
        return self.draws.u("overreach", k) < self.b["p_overreach"]

    def invalid_call(self, n: int, actor: str = "") -> bool:
        return self.draws.u("invalid" + actor, n) < self.b["p_invalid_args"]

    def rereads(self, k: int) -> bool:
        return self.draws.u("reread", k) < self.b["p_reread"]

    def suite_catches_hack(self) -> bool:
        return self.draws.u("suite") < self.b["p_suite_catch"]

    def handoff_keeps_context(self) -> bool:
        return self.draws.u("handoff") < self.b["handoff_fidelity"]

    def reviewer_rejects(self, k: int, variant: str) -> bool:
        if variant == "hack":
            return self.draws.u("review_catch", k) < self.b["review_catch"]
        return self.draws.u("review_false", k) < self.b["review_false_reject"]

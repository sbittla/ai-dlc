"""The agent loop and its stopping conditions (added in 4.24.0; ADR-024).

An agent loop observes, plans, acts and decides whether to stop. The first three are the model's job.
The fourth is not: whether a run may continue is decided here, by code, before every step, from the
run's budget and its own history. A model that believes it is close to done does not get to spend more.

Stopping conditions, checked in this order before each step:

  budget:<kind>               a limit of the run's budget has been reached (steps, model_calls, usd, seconds)
  repeated_failure:<sig>      the same failure signature has been seen `repeat_limit` times in the run,
                              such as one test failing three times or one review finding repeated
                              (Chapter 9's stop signal, made mechanical)
  no_progress                 none of the last `no_progress_limit` steps observed a state not seen before

Ending a run is also decided outside the model. "Finish" is accepted only if `done_check` agrees, for
example that the approved tests pass; otherwise it is recorded as a failure (`not_done`). "Hand back" ends
the run for a person, with the agent's reason. A disabled agent ends as `revoked`, and a gated call
pauses the run as `awaiting_approval` with its state saved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from .boundary import AwaitingApproval, ToolBoundary
from .budget import BudgetExceeded
from .session import AgentRevoked


@dataclass(frozen=True)
class StopRules:
    repeat_limit: int = 3
    no_progress_limit: int = 6

    def __post_init__(self) -> None:
        if self.repeat_limit < 1 or self.no_progress_limit < 1:
            raise ValueError("stop limits must be positive")


@dataclass(frozen=True)
class StepRecord:
    tool: str
    ok: bool
    failure: str | None = None
    progress: str | None = None


def stop_reason(meter, history: list[StepRecord], rules: StopRules) -> str | None:
    """The first stopping condition that holds, or None if the run may take another step.

    1. Budget: call meter.check(); if it raises BudgetExceeded, return f"budget:{kind}".
    2. Repeated failure: walk `history` in order, counting each non-None `failure`; as soon as one
       signature's count reaches rules.repeat_limit, return f"repeated_failure:{signature}".
    3. No progress: if history has at least rules.no_progress_limit records, and none of the last
       no_progress_limit records has a `progress` key that no earlier record (anywhere before it)
       had, return "no_progress". A record whose progress is None never counts as new.
    """
    try:
        meter.check()
    except BudgetExceeded as exc:
        return f"budget:{exc.kind}"
    counts: dict[str, int] = {}
    for record in history:
        if record.failure is not None:
            counts[record.failure] = counts.get(record.failure, 0) + 1
            if counts[record.failure] >= rules.repeat_limit:
                return f"repeated_failure:{record.failure}"
    n = rules.no_progress_limit
    if len(history) >= n:
        seen: set[str] = set()
        new_flags = []
        for record in history:
            new_flags.append(record.progress is not None and record.progress not in seen)
            if record.progress is not None:
                seen.add(record.progress)
        if not any(new_flags[-n:]):
            return "no_progress"
    return None


@dataclass(frozen=True)
class Decision:
    """One model call's choice, and what the call cost."""

    action: str                       # "tool", "finish" or "hand_back"
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float
    cached_tokens: int = 0
    tool: str | None = None
    args: dict = field(default_factory=dict)
    note: str = ""


class Policy(Protocol):
    actor: str

    def next_call(self) -> tuple[str, int, int, int]:
        """(model, input tokens, output allowance, cached tokens) of the call `decide` is about to make."""
        ...

    def decide(self) -> Decision: ...

    def observe(self, tool: str, result) -> None: ...


@dataclass
class LoopResult:
    status: str                       # finished, handed_back, stopped, revoked, delegation_expired, awaiting_approval
    reason: str
    history: list[StepRecord]
    approval_id: str | None = None


def run_loop(policy: Policy, boundary: ToolBoundary, rules: StopRules, done_check: Callable[[], bool],
             history: list[StepRecord] | None = None,
             checkpoint: Callable[[list[StepRecord]], None] | None = None) -> LoopResult:
    """Run `policy` through `boundary` until a stopping condition, a finish, a hand-back or a pause.

    `history` lets a resumed run continue with the records it had, so repeated failures and stalls are
    counted across a restart, as the budget is.
    """
    history = list(history or [])
    meter = boundary.meter
    while True:
        reason = stop_reason(meter, history, rules)
        if reason is not None:
            return LoopResult("stopped" if reason.startswith("budget") else "handed_back", reason, history)
        model, input_tokens, allowance, cached = policy.next_call()
        estimate = meter.estimate(model, input_tokens, allowance, cached)  # computed here, not by the policy
        try:
            meter.admit(estimate)
        except BudgetExceeded as exc:
            return LoopResult("stopped", f"budget:{exc.kind}", history)
        decision = policy.decide()
        cost = meter.charge_model(policy.actor, decision.model, decision.input_tokens, decision.output_tokens,
                                  decision.seconds, decision.cached_tokens)
        if cost > estimate + 1e-12:
            meter.overruns += 1
        if decision.action == "finish":
            if done_check():
                return LoopResult("finished", decision.note or "done", history)
            history.append(StepRecord("finish", False, "not_done"))
            policy.observe("finish", None)
        elif decision.action == "hand_back":
            return LoopResult("handed_back", f"agent:{decision.note}", history)
        else:
            try:
                result = boundary.call(decision.tool, decision.args)
            except AgentRevoked as exc:
                return LoopResult(exc.status, exc.code, history)
            except AwaitingApproval as exc:
                return LoopResult("awaiting_approval", decision.tool, history, exc.approval_id)
            except BudgetExceeded as exc:
                return LoopResult("stopped", f"budget:{exc.kind}", history)
            history.append(StepRecord(decision.tool, result.ok, result.failure, result.progress))
            policy.observe(decision.tool, result)
        if checkpoint is not None:
            checkpoint(history)

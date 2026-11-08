"""The escalation slice's data types (spec ESC-SPEC-1, section Contracts).

Every dataclass here that crosses the slice boundary has a definition of the
same name in specs/001-escalation-rules/contracts/escalation-rules.schema.json,
with the same fields. Lab 5.2's drift check compares the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

PRIORITIES = ("P1", "P2", "P3", "P4")
STATUSES = ("not_applicable", "acknowledged", "active", "complete")
ERROR_CODES = (
    "not_rule_editor",
    "unsupported_priority",
    "no_steps",
    "steps_not_numbered",
    "delay_out_of_range",
    "delays_not_increasing",
    "no_targets",
    "target_not_user",
    "target_not_in_workspace",
    "target_cannot_view_project",
)
RULE_EDITORS = ("Owner", "Admin")  # D2
MIN_DELAY_MINUTES = 5  # D1
MAX_DELAY_MINUTES = 240  # D1


@dataclass(frozen=True)
class Step:
    number: int  # 1, 2, ... in order
    delay_seconds: int  # after the task's priority was set
    targets: tuple[int, ...]  # workspace user IDs, never addresses


@dataclass(frozen=True)
class Rule:
    rule_id: str
    project_id: int
    priority: str  # one of PRIORITIES
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class EscalationState:
    """What Relay knows about one task's escalation. Internal: not part of the contract."""

    task_id: int
    priority: str | None = None  # set or confirmed by a person (ESC-N01)
    priority_set_at: datetime | None = None  # UTC
    suggested_priority: str | None = None  # the triage model's suggestion; evaluate() never reads it
    suggested_confidence: int | None = None  # percent
    acknowledged_at: datetime | None = None  # UTC
    fired_steps: frozenset[int] = frozenset()


@dataclass(frozen=True)
class StepDecision:
    step: int
    targets: tuple[int, ...]
    due_at: datetime  # UTC


@dataclass(frozen=True)
class Evaluation:
    spec_version: str
    task_id: int
    rule_id: str
    evaluated_at: datetime  # UTC
    status: str  # one of STATUSES
    fire: tuple[StepDecision, ...]  # steps to fire now, in step order
    next_due_at: datetime | None  # when the next unfired step is due, if any


@dataclass(frozen=True)
class Rejection:
    code: str  # one of ERROR_CODES
    message: str
    subject: str | None  # the step, user or value the message names


class RuleRejected(ValueError):
    """Raised by validate_rule when Relay must refuse to save a rule."""

    def __init__(self, code: str, message: str, subject: str | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message)
        self.rejection = Rejection(code, message, subject)

    @property
    def code(self) -> str:
        return self.rejection.code

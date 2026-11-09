"""The escalation engine's data types (spec ESC-SPEC-1, section Contracts).

Every dataclass here that crosses the engine's boundary has a definition of the
same name in specs/001-escalation-rules/contracts/escalation-rules.schema.json,
with the same fields in the same order. Lab 5.2's drift check and the contract
tests compare the two.
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
    "business_hours_required",
    "business_hours_not_allowed",
    "business_hours_invalid",
)
RULE_EDITORS = ("Owner", "Admin")  # D2
RULE_PRIORITIES = PRIORITIES  # 1.1.0: P2 to P4 rules count business hours (ESC-R07, ADR-010)
CALENDAR_PRIORITIES = ("P1",)  # P1 steps count calendar minutes, like Relay's on-call policy (ESC-R04)
MIN_DELAY_MINUTES = 5  # D1
MAX_DELAY_MINUTES = 240  # D1; for business-hours rules, 240 business minutes is ESC-R07's 4 hours
WEEKDAYS = (1, 2, 3, 4, 5, 6, 7)  # ISO weekday numbers, Monday = 1
DEFAULT_BUSINESS_DAYS = (1, 2, 3, 4, 5)  # D10: a new rule's business days are Monday to Friday
ZONE_NAMES = ("Pacific/Pago_Pago", "Pacific/Honolulu", "America/Los_Angeles", "America/New_York", "UTC",
              "Europe/London", "Europe/Berlin", "Asia/Kolkata", "Asia/Tokyo", "Australia/Sydney", "Pacific/Auckland",
              "Pacific/Tongatapu", "Pacific/Chatham", "Pacific/Kiritimati")  # relay.timezones' 14 zones (ADR-010)
EMAIL_KINDS = ("escalation", "summary", "rule_notice")  # 1.2.0: rule_notice for P1 rule changes (ESC-N06)
WEBHOOK_EVENTS = ("task.escalated",)


@dataclass(frozen=True)
class Step:
    number: int  # 1, 2, ... in order
    delay_minutes: int  # after the task's priority was set; business minutes for P2 to P4 rules
    targets: tuple[int, ...]  # workspace user IDs, never addresses


@dataclass(frozen=True)
class BusinessHours:
    """When a P2 to P4 rule's clock runs (ESC-R07, D4, D10): local wall-clock hours in the rule's zone."""

    start: str  # "HH:MM", local time
    end: str  # "HH:MM", local time, later than start on the same day
    time_zone: str  # a zone in relay.escalation.hours.ZONES
    days: tuple[int, ...] = DEFAULT_BUSINESS_DAYS  # ISO weekdays the hours apply on


@dataclass(frozen=True)
class Rule:
    rule_id: str
    project_id: int
    priority: str  # one of PRIORITIES
    steps: tuple[Step, ...]
    name: str | None = None  # shown in escalation emails and events (ESC-R11, ESC-N07)
    business_hours: BusinessHours | None = None  # required for P2 to P4, refused for P1


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


@dataclass(frozen=True)
class RuleDeleted:
    """The delete route's answer (spec 1.2.0, B8): which rule, when, and how many rule notices were written."""

    rule_id: str
    deleted_at: datetime
    notices: int  # one per Owner and Admin for a P1 rule; 0 otherwise


@dataclass(frozen=True)
class EmailMessage:
    """One email for delivery. The adapter resolves `to_user` to an address inside Relay (SEC-04)."""

    kind: str  # one of EMAIL_KINDS
    to_user: int
    subject: str
    body: str


@dataclass(frozen=True)
class WebhookEvent:
    """The body of one signed task.escalated event (ESC-R09). IDs, names, numbers and times only."""

    event: str  # one of WEBHOOK_EVENTS
    spec_version: str
    task_id: int
    link: str
    priority: str
    project_name: str
    rule_id: str
    rule_name: str
    step: int
    targets: tuple[int, ...]
    delay_started_at: datetime  # UTC
    fired_at: datetime  # UTC


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

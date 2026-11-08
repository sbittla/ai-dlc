"""What an escalation sends: emails and signed webhook events (spec ESC-SPEC-1 1.1.0, behaviour B5).

ESC-R09: one email per target and one task.escalated event per fired step.
ESC-R11: every message names the rule, the step, when its delay started and
when it fired, in UTC. ESC-N07 and SEC-04: no task content, only the task's
link, its priority, the project's name, the rule's name and the step number.

None of these functions receives a Task, so none of them can copy a title into
a message. That is deliberate: the privacy rule is enforced by what the code
is given, and a policy test checks the signatures.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta

from ..models import Project
from . import SPEC_VERSION
from .contract import to_document
from .model import EmailMessage, Rule, StepDecision, WebhookEvent

SIGNATURE_HEADER = "X-Relay-Signature"


def task_link(base_url: str, project_id: int, task_id: int) -> str:
    """The task's link: Relay's web address for it. Opening it needs a Relay login."""
    return f"{base_url.rstrip('/')}/projects/{project_id}/tasks/{task_id}"


def rule_label(rule: Rule) -> str:
    """The rule's name for messages, on one line; its ID if it has no name."""
    return " ".join((rule.name or rule.rule_id).split())


def utc_minute(instant: datetime) -> str:
    """'2026-11-24 02:30 UTC'."""
    if instant.utcoffset() != timedelta(0):
        raise ValueError("times in messages must be UTC")
    return instant.strftime("%Y-%m-%d %H:%M UTC")


def escalation_email(decision: StepDecision, to_user: int, rule: Rule, project: Project, task_id: int,
                     link: str, delay_started_at: datetime, fired_at: datetime) -> EmailMessage:
    """The email one target receives when a step fires (ESC-R09, ESC-R11, ESC-N07)."""
    raise NotImplementedError("TODO (Lab 8.1, step 5: build the messages, spec B5)")


def escalation_event(decision: StepDecision, rule: Rule, project: Project, task_id: int, link: str,
                     delay_started_at: datetime, fired_at: datetime) -> WebhookEvent:
    """The task.escalated event for one fired step: one per step, whatever the number of targets."""
    raise NotImplementedError("TODO (Lab 8.1, step 5: build the messages, spec B5)")


def event_body(event: WebhookEvent) -> bytes:
    """The exact bytes sent, and signed: compact JSON with sorted keys, UTF-8."""
    raise NotImplementedError("TODO (Lab 8.1, step 5: build the messages, spec B5)")


def sign(body: bytes, secret: bytes) -> str:
    """The X-Relay-Signature value: 'sha256=' and the hex HMAC-SHA256 of the body bytes."""
    raise NotImplementedError("TODO (Lab 8.1, step 5: build the messages, spec B5)")


def summary_email(to_user: int, held: list[tuple[int, str, str, int]], hour_ends: datetime) -> EmailMessage:
    """The one email a capped target gets when the hour ends (ESC-N04): (task_id, link, rule, step) each."""
    lines = [f"Relay held {len(held)} escalation email(s) for you in the hour ending {utc_minute(hour_ends)},",
             "because you had already received 20 that hour.", ""]
    lines += [f"- Step {step} of {rule}: {link}" for _task_id, link, rule, step in held]
    return EmailMessage("summary", to_user, f"[Relay] {len(held)} held escalation(s)", "\n".join(lines))

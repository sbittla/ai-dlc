"""What an escalation sends: emails and signed webhook events (spec ESC-SPEC-1 1.1.0, behaviour B5).

ESC-R09: one email per target and one task.escalated event per fired step.
ESC-N06 (spec 1.2.0, B8): one rule notice to the Owner and to every Admin when
a P1 rule is changed or deleted, naming the rule and the person who acted.
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
    subject = f"[Relay] {rule.priority} escalation in {project.name}: step {decision.step} of {rule_label(rule)}"
    body = "\n".join([
        f"A {rule.priority} task in {project.name} has not been acknowledged.",
        "",
        f"Rule: {rule_label(rule)} ({rule.rule_id})",
        f"Step: {decision.step}",
        f"Delay started: {utc_minute(delay_started_at)}",
        f"Step fired: {utc_minute(fired_at)}",
        "",
        f"Open the task: {link}",
        f"Relay task {task_id}",
    ])
    return EmailMessage("escalation", to_user, " ".join(subject.split()), body)


def escalation_event(decision: StepDecision, rule: Rule, project: Project, task_id: int, link: str,
                     delay_started_at: datetime, fired_at: datetime) -> WebhookEvent:
    """The task.escalated event for one fired step: one per step, whatever the number of targets."""
    return WebhookEvent("task.escalated", SPEC_VERSION, task_id, link, rule.priority, project.name, rule.rule_id,
                        rule_label(rule), decision.step, decision.targets, delay_started_at, fired_at)


def event_body(event: WebhookEvent) -> bytes:
    """The exact bytes sent, and signed: compact JSON with sorted keys, UTF-8."""
    return json.dumps(to_document(event), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign(body: bytes, secret: bytes) -> str:
    """The X-Relay-Signature value: 'sha256=' and the hex HMAC-SHA256 of the body bytes."""
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def rules_link(base_url: str, project_id: int) -> str:
    """The project's escalation-rules page in Relay. Opening it needs a Relay login."""
    return f"{base_url.rstrip('/')}/projects/{project_id}/escalation-rules"


def rule_notice_email(action: str, before: Rule | None, after: Rule | None, project: Project, actor_id: int,
                      actor_role: str, at: datetime, link: str, to_user: int) -> EmailMessage:
    """The notice the Owner and each Admin receive when a P1 rule is changed or deleted (ESC-N06, ESC-AC25).

    `action` is "changed" or "deleted". The actor is named by role and user ID,
    the form spec 1.2.0 defines for "naming" a person in a message: user names
    are Confidential (SEC-04), and every recipient can open the link and see
    who the user is inside Relay.
    """
    if action not in ("changed", "deleted"):
        raise ValueError("action must be 'changed' or 'deleted'")
    rule = before if before is not None else after
    if rule is None:
        raise ValueError("a notice needs the rule before or after the change")
    label = rule_label(rule)
    named = f"{label} ({rule.rule_id})" if rule.name else rule.rule_id
    subject = f"[Relay] P1 escalation rule {action} in {project.name}: {label}"
    lines = [f"{actor_role} user {actor_id} {action} the escalation rule {named} in {project.name}",
             f"at {utc_minute(at)}.", ""]
    if action == "deleted":
        lines.append(f"Before: {_shape(before)}. Its steps no longer fire for any task.")
    else:
        lines += [f"Before: {_shape(before)}.", f"After: {_shape(after)}."]
    lines += ["", f"Review the project's rules: {link}",
              "You receive this because you are the workspace's Owner or an Admin (ESC-N06)."]
    return EmailMessage("rule_notice", to_user, " ".join(subject.split()), "\n".join(lines))


def _shape(rule: Rule | None) -> str:
    """'P1, steps at 10 and 20 minutes, 3 targets' - priority, delays and target count; no names or addresses."""
    if rule is None:
        return "no rule"
    delays = [str(s.delay_minutes) for s in rule.steps]
    joined = delays[0] if len(delays) == 1 else ", ".join(delays[:-1]) + " and " + delays[-1]
    targets = len({t for s in rule.steps for t in s.targets})
    unit = "business minutes" if rule.business_hours is not None else "minutes"
    return f"{rule.priority}, step{'s' if len(delays) > 1 else ''} at {joined} {unit}, {targets} target(s)"


def summary_email(to_user: int, held: list[tuple[int, str, str, int]], hour_ends: datetime) -> EmailMessage:
    """The one email a capped target gets when the hour ends (ESC-N04): (task_id, link, rule, step) each."""
    lines = [f"Relay held {len(held)} escalation email(s) for you in the hour ending {utc_minute(hour_ends)},",
             "because you had already received 20 that hour.", ""]
    lines += [f"- Step {step} of {rule}: {link}" for _task_id, link, rule, step in held]
    return EmailMessage("summary", to_user, f"[Relay] {len(held)} held escalation(s)", "\n".join(lines))

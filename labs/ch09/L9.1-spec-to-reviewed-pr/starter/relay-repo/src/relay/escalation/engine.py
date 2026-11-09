"""The escalation engine: rules saved and deleted with audit, priorities and acknowledgements, and evaluation passes.

Spec ESC-SPEC-1 1.2.0, behaviours B4 to B6 and B8; ADR-011, ADR-016. Every
function takes the store and an explicit time, and reads no clock. The worker
calls `run_pass` on each loop (ADR-017); the service calls the rest (ADR-009).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from ..models import Project, Task, User
from ..roles import can_view_project
from .contract import rule_from_document, to_document, to_rule_document
from .delivery import (SIGNATURE_HEADER, escalation_email, escalation_event, event_body, rule_label, rule_notice_email,
                       rules_link, sign, summary_email, task_link)
from .evaluate import evaluate
from .model import PRIORITIES, Rule, RuleRejected
from .rules import validate_rule
from .store import EscalationStore

UTC = timezone.utc
FLOOD_CAP_PER_HOUR = 20  # ESC-N04, D7: escalation emails per target per hour, across all rules
PRIORITY_SETTERS = ("Owner", "Admin", "Member")  # ESC-R01


class RuleIdInUse(ValueError):
    """The rule ID belongs to a rule in another project, or to a deleted rule; rule IDs are unique in a workspace."""


class RuleNotFound(LookupError):
    """No live rule with this ID in this project: never saved, deleted already, or another project's."""


@dataclass(frozen=True)
class Webhook:
    """The workspace's webhook endpoint. The secret is Restricted: it signs, and is never stored or sent."""

    url: str
    secret: bytes = field(repr=False)


@dataclass(frozen=True)
class EngineConfig:
    link_base: str  # e.g. "https://relay.example/ws-demo"
    webhook: Webhook | None = None


@dataclass
class PassResult:
    steps_fired: int = 0
    emails: int = 0
    held: int = 0
    events: int = 0
    summaries: int = 0
    cannot_evaluate: int = 0  # (task, rule) pairs skipped this pass because their timing raised an error


# -------------------------------------------------------------------- rules (B4)

def save_rule(store: EscalationStore, rule: Rule, editor: User, project: Project, users: Mapping[int, User],
              at: datetime, link_base: str = "") -> bool:
    """Validate on the server, then save with an audit entry. True if created, False if replaced.

    A refused rule raises RuleRejected, is audited as refused with its code,
    and leaves the saved rule unchanged (ESC-N03, ESC-AC06, ESC-AC21, ESC-AC24).
    Replacing a rule that is P1 before or after the change writes a rule notice
    to the Owner and every Admin in the same transaction (ESC-N06, B8).
    """
    before = store.rule_document(rule.rule_id, include_deleted=True)
    deleted = store.is_deleted(rule.rule_id)
    if before is not None and (deleted or before["project_id"] != project.id):
        # Rule IDs are unique in a workspace, and a deleted rule's ID is never reused (ADR-016).
        store.add_audit(at, editor.id, rule.rule_id, "refused", "rule_id_deleted" if deleted else "rule_id_in_use")
        raise RuleIdInUse(rule.rule_id)
    try:
        validate_rule(rule, editor, project, users)
    except RuleRejected as refused:
        store.add_audit(at, editor.id, rule.rule_id, "refused", refused.code)
        raise
    after = to_rule_document(rule)
    store.begin()
    try:
        store.put_rule(rule, after, at)
        store.add_audit(at, editor.id, rule.rule_id, "saved", None, before, after)
        if before is not None and "P1" in (before["priority"], rule.priority):
            _notify_rule_change(store, "changed", rule_from_document(before), rule, project, editor, users, at,
                                link_base)
        store.commit()
    except Exception:
        store.rollback()
        raise
    return before is None


def delete_rule(store: EscalationStore, rule_id: str, editor: User, project: Project, users: Mapping[int, User],
                at: datetime, link_base: str = "") -> Rule:
    """Delete a live rule of `project` with an audit entry, and return it (spec 1.2.0, B8; ADR-016).

    Only Owners and Admins may delete (D2): anyone else raises RuleRejected
    with `not_rule_editor`, audited as refused, and the rule is unchanged. A
    rule that is absent, already deleted or another project's raises
    RuleNotFound. The rule stops firing at once. Deleting a P1 rule writes a
    rule notice to the Owner and every Admin in the same transaction, so the
    notice exists as soon as the deletion does (ESC-N06, ESC-AC25).
    """
    # TODO (README step 4: spec 1.2.0, B8; ADR-016)
    raise NotImplementedError("TODO: delete_rule (README step 4: spec 1.2.0, B8; ADR-016)")


def notice_recipients(users: Mapping[int, User]) -> list[int]:
    """The Owner and every Admin of the workspace, by user ID (ESC-N06). Never empty for a valid workspace."""
    return sorted(u.id for u in users.values() if u.role in ("Owner", "Admin"))


def _notify_rule_change(store, action, before, after, project, editor, users, at, link_base) -> None:
    link = rules_link(link_base, project.id)
    for to_user in notice_recipients(users):
        message = rule_notice_email(action, before, after, project, editor.id, editor.role, at, link, to_user)
        rule_id = (before or after).rule_id
        store.add_outbox(f"notice:{rule_id}:{action}:{at.isoformat()}:{to_user}", at, "email", message.kind,
                         str(to_user), {}, _json(message))


def refuse(store: EscalationStore, actor: User, rule_id: str, code: str, at: datetime,
           problems: list[str] | None = None) -> None:
    """Audit a change refused before validation, such as a document that breaks the contract (ESC-AC24)."""
    store.add_audit(at, actor.id, rule_id, "refused", code, problems=problems)


def rules_for(store: EscalationStore, project_id: int) -> list[Rule]:
    return [rule_from_document(d) for d in store.rule_documents(project_id)]


# -------------------------------------------------------------------- people and the model (B6)

def set_priority(store: EscalationStore, task: Task, project: Project, user: User, priority: str,
                 at: datetime) -> None:
    """A person sets or confirms a task's priority (ESC-R01, ESC-N01). The clock restarts at `at`."""
    if user.role not in PRIORITY_SETTERS or not can_view_project(user, project) or task.project_id != project.id:
        raise PermissionError(f"user {user.id} cannot set the priority of task {task.id}")
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
    store.ensure_state(task.id, project.id)
    store.set_priority(task.id, priority, user.id, at)
    store.add_activity(task.id, at, "priority_set", {"priority": priority, "by": user.id})


def record_suggestion(store: EscalationStore, task: Task, priority: object, confidence: object,
                      at: datetime) -> None:
    """Store the triage model's suggestion for display. It never sets the priority (D3, SEC-03).

    The model's output is untrusted input: anything but a known priority and a
    whole-number percentage is refused with ValueError, and nothing is stored.
    """
    if priority not in PRIORITIES or type(confidence) is not int or not 0 <= confidence <= 100:
        raise ValueError("a suggestion is a priority P1 to P4 and a whole-number confidence from 0 to 100")
    store.ensure_state(task.id, task.project_id)
    store.set_suggestion(task.id, priority, confidence)
    store.add_activity(task.id, at, "suggested", {"priority": priority, "confidence": confidence})


def acknowledge(store: EscalationStore, task: Task, project: Project, user: User, at: datetime) -> bool:
    """A person who can view the project acknowledges the task (ESC-R02). True the first time only."""
    if not can_view_project(user, project) or task.project_id != project.id:
        raise PermissionError(f"user {user.id} cannot acknowledge task {task.id}")
    store.ensure_state(task.id, project.id)
    first = store.set_acknowledged(task.id, user.id, at)
    if first:
        store.add_activity(task.id, at, "acknowledged", {"by": user.id})
    return first


def escalation_view(store: EscalationStore, task: Task, project: Project, viewer: User) -> dict:
    """The task's escalation panel, as `viewer` sees it (ESC-AC01, ESC-AC03, ESC-AC18)."""
    if not can_view_project(viewer, project) or task.project_id != project.id:
        raise PermissionError(f"user {viewer.id} cannot view project {project.id}")
    state = store.state(task.id)
    set_by, acked_by = store.state_people(task.id)
    suggestion = None
    if state.suggested_priority is not None:
        suggestion = f"Suggested: {state.suggested_priority} ({state.suggested_confidence}%)"
    return {
        "task_id": task.id,
        "priority": state.priority,
        "priority_set_at": None if state.priority_set_at is None else to_document(state.priority_set_at),
        "priority_set_by": set_by,
        "suggestion": suggestion,
        "acknowledged_at": None if state.acknowledged_at is None else to_document(state.acknowledged_at),
        "acknowledged_by": acked_by,
        "activity": store.activity(task.id),
    }


# -------------------------------------------------------------------- the evaluation pass (B5)

def _hour_end(now: datetime) -> datetime:
    start = now.replace(minute=0, second=0, microsecond=0)
    return start + timedelta(hours=1)


def run_pass(store: EscalationStore, tasks: Mapping[int, Task], projects: Mapping[int, Project],
             config: EngineConfig, now: datetime) -> PassResult:
    """Fire every due step once, write its messages to the outbox, and send summaries whose hour has ended.

    One transaction per pass, with a savepoint per task and rule: a rule whose
    timing raises ValueError is rolled back alone, recorded once on the task as
    `cannot_evaluate`, counted, and skipped; the others still fire. For each fired step: one escalation email per
    target, unless the target has had 20 in the past hour (then the email is
    held and the task's activity says so), and one signed task.escalated event
    if the workspace has a webhook. Webhook events are not capped.
    """
    if now.utcoffset() != timedelta(0):
        raise ValueError("now must be an aware UTC datetime")
    result = PassResult()
    store.begin()
    try:
        for task_id, project_id in store.live_tasks():
            task, project = tasks.get(task_id), projects.get(project_id)
            if task is None or project is None:
                continue
            for rule in rules_for(store, project_id):
                # Each (task, rule) is isolated: one that cannot be timed, such as a business-hours delay
                # running past the zone table (ADR-010), is skipped and recorded, and every other rule fires.
                store.savepoint()
                try:
                    _fire_rule(store, rule, task, project, config, now, result)
                except ValueError as exc:
                    store.rollback_to_savepoint()
                    _cannot_evaluate(store, task, rule, now, exc, result)
                store.release_savepoint()
        _send_summaries(store, config, now, result)
        store.commit()
    except Exception:
        store.rollback()
        raise
    return result


def _fire_rule(store, rule, task, project, config, now, result) -> None:
    state = replace(store.state(task.id), fired_steps=store.fired_steps(task.id, rule.rule_id))
    evaluation = evaluate(rule, task, state, now)
    link = task_link(config.link_base, project.id, task.id)
    for decision in evaluation.fire:
        if not store.mark_fired(task.id, rule.rule_id, decision.step, now):
            continue
        result.steps_fired += 1
        started = state.priority_set_at
        for target in decision.targets:
            key = f"email:{task.id}:{rule.rule_id}:{decision.step}:{target}"
            if store.escalation_emails_since(target, now - timedelta(hours=1)) >= FLOOD_CAP_PER_HOUR:
                store.hold(target, task.id, rule.rule_id, decision.step, now, _hour_end(now))
                store.add_activity(task.id, now, "not_emailed", {"reason": "flood_cap", "step": decision.step,
                                                                 "target": target, "rule_id": rule.rule_id})
                result.held += 1
                continue
            message = escalation_email(decision, target, rule, project, task.id, link, started, now)
            store.add_outbox(key, now, "email", message.kind, str(target), {}, _json(message))
            result.emails += 1
        store.add_activity(task.id, now, "escalated", {"rule_id": rule.rule_id, "step": decision.step,
                                                       "targets": list(decision.targets)})
        if config.webhook is not None:
            body = event_body(escalation_event(decision, rule, project, task.id, link, started, now))
            headers = {"Content-Type": "application/json", "X-Relay-Event": "task.escalated",
                       SIGNATURE_HEADER: sign(body, config.webhook.secret)}
            store.add_outbox(f"webhook:{task.id}:{rule.rule_id}:{decision.step}", now, "webhook", "task.escalated",
                             config.webhook.url, headers, body.decode("utf-8"))
            result.events += 1


def _cannot_evaluate(store, task, rule, now, exc, result) -> None:
    result.cannot_evaluate += 1
    already = any(a["kind"] == "cannot_evaluate" and a.get("rule_id") == rule.rule_id for a in store.activity(task.id))
    if not already:
        store.add_activity(task.id, now, "cannot_evaluate", {"rule_id": rule.rule_id, "reason": str(exc)[:200]})


def _send_summaries(store, config, now, result) -> None:
    for target, hour_ends, items in store.summaries_due(now):
        held = []
        for task_id, rule_id, step in items:
            document = store.rule_document(rule_id, include_deleted=True)  # a held step outlives its rule's deletion
            rule = rule_from_document(document) if document else None
            project_id = document["project_id"] if document else 0
            held.append((task_id, task_link(config.link_base, project_id, task_id),
                         rule_label(rule) if rule else rule_id, step))
        message = summary_email(target, held, hour_ends)
        store.add_outbox(f"summary:{target}:{hour_ends.isoformat()}", now, "email", "summary", str(target), {},
                         _json(message))
        store.mark_summarized(target, hour_ends)
        result.summaries += 1


def _json(message) -> str:
    return json.dumps(to_document(message), sort_keys=True)

"""Rule evaluation: which steps fire now? (spec ESC-SPEC-1, behaviour B2; SEC-03, SEC-04)."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import Task
from . import SPEC_VERSION
from .model import EscalationState, Evaluation, Rule, StepDecision


def evaluate(rule: Rule, task: Task, state: EscalationState, now: datetime) -> Evaluation:
    """Decide which of `rule`'s steps fire for `task` at `now` (an aware UTC datetime).

    - not_applicable: the task has no priority set by a person, or a different
      priority from the rule's. A suggested priority is never read (D3).
    - acknowledged: the task was acknowledged; remaining steps are cancelled (D9).
    - otherwise each step is due at priority_set_at + delay_minutes. Every due
      step that has not already fired is returned in `fire`, in step order; a
      step never fires twice (D9). A step is due when now >= its due time.
    - active if an unfired step remains after this evaluation, else complete.

    The result carries IDs, step numbers and times only, never the task's title
    (ESC-N07, SEC-04).
    """
    if task.id != state.task_id:
        raise ValueError(f"state is for task {state.task_id}, not {task.id}")
    if task.project_id != rule.project_id:
        raise ValueError(f"task {task.id} is not in rule {rule.rule_id}'s project")
    if now.utcoffset() != timedelta(0):
        raise ValueError("now must be an aware UTC datetime")

    def result(status: str, fire: tuple[StepDecision, ...] = (), next_due: datetime | None = None) -> Evaluation:
        return Evaluation(SPEC_VERSION, task.id, rule.rule_id, now, status, fire, next_due)

    if state.priority != rule.priority or state.priority_set_at is None:
        return result("not_applicable")
    if state.acknowledged_at is not None:
        return result("acknowledged")
    fire = []
    next_due = None
    for step in rule.steps:
        if step.number in state.fired_steps:
            continue
        due = state.priority_set_at + timedelta(seconds=step.delay_seconds)
        if now >= due:
            fire.append(StepDecision(step.number, step.targets, due))
        elif next_due is None:
            next_due = due
    return result("active" if next_due is not None else "complete", tuple(fire), next_due)

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
    raise NotImplementedError('evaluate')

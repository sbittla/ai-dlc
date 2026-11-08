"""Rule validation: may Relay save this rule? (spec ESC-SPEC-1, behaviour B1; SEC-01, SEC-02)."""

from __future__ import annotations

from collections.abc import Mapping

from ..models import Project, User
from ..roles import can_view_project
from .model import MAX_DELAY_MINUTES, MIN_DELAY_MINUTES, PRIORITIES, RULE_EDITORS, Rule, RuleRejected


def validate_rule(rule: Rule, editor: User, project: Project, users: Mapping[int, User]) -> Rule:
    """Return `rule` unchanged if `editor` may save it for `project`; raise RuleRejected if not.

    `users` maps every workspace user's ID to the user. Checks run in this
    order, and the first failure is raised:

    1. editor: only Owners and Admins change rules (D2)       -> not_rule_editor
    2. priority: one of P1-P4                                  -> unsupported_priority
    3. steps: at least one, numbered 1, 2, ... in order        -> no_steps, steps_not_numbered
    4. each step, in order:
       a. delay: a whole number of minutes from 5 to 240       -> delay_out_of_range
       b. delay greater than the previous step's (D1)          -> delays_not_increasing
       c. at least one target (ESC-N06)                        -> no_targets
       d. each target: an int user ID (ESC-N05)                -> target_not_user
          in the workspace                                     -> target_not_in_workspace
          who can view the project (ESC-R08)                   -> target_cannot_view_project

    Messages name what was refused: the allowed range for delays (ESC-AC10)
    and the user's name and role for targets (ESC-AC14). Validation is a pure
    function, so a refused rule is never partly applied.
    """
    if project.id != rule.project_id:
        raise ValueError(f"rule {rule.rule_id} belongs to project {rule.project_id}, not {project.id}")
    if editor.role not in RULE_EDITORS:
        raise RuleRejected("not_rule_editor",
                           f"{editor.name} ({editor.role}) cannot change escalation rules; "
                           "only Owners and Admins can.", str(editor.id))
    if rule.priority not in PRIORITIES:
        raise RuleRejected("unsupported_priority", f"Priority {rule.priority!r} is not one of P1-P4.",
                           str(rule.priority))
    if not rule.steps:
        raise RuleRejected("no_steps", "A rule needs at least one step.")
    previous = None
    for n, step in enumerate(rule.steps, 1):
        if step.number != n:
            raise RuleRejected("steps_not_numbered", f"Step {n} is numbered {step.number}.", f"step {n}")
        delay = step.delay_minutes
        if type(delay) is not int or not MIN_DELAY_MINUTES <= delay <= MAX_DELAY_MINUTES:
            raise RuleRejected("delay_out_of_range",
                               f"Step {n} delay of {delay} minutes is outside the allowed range of "
                               f"{MIN_DELAY_MINUTES} to {MAX_DELAY_MINUTES} minutes.", f"step {n}")
        if previous is not None and delay <= previous:
            raise RuleRejected("delays_not_increasing",
                               f"Step {n} delay of {delay} minutes must be greater than step {n - 1}'s "
                               f"{previous} minutes.", f"step {n}")
        previous = delay
        if not step.targets:
            raise RuleRejected("no_targets", f"Step {n} has no targets; every step needs at least one.",
                               f"step {n}")
        for target in step.targets:
            if type(target) is not int:
                raise RuleRejected("target_not_user",
                                   f"Step {n} target {target!r} is not a workspace user ID; email addresses, "
                                   "phone numbers and URLs are not accepted.", repr(target))
            user = users.get(target)
            if user is None:
                raise RuleRejected("target_not_in_workspace",
                                   f"Step {n} target {target} is not a user in this workspace.", str(target))
            if not can_view_project(user, project):
                raise RuleRejected("target_cannot_view_project",
                                   f"{user.name} ({user.role}) cannot view project {project.name}, "
                                   f"so cannot be a target of its rules.", user.name)
    return rule

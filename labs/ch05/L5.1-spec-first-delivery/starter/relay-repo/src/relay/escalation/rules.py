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
    raise NotImplementedError('validate_rule')

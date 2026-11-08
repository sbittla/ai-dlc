"""Rule validation: may Relay save this rule? (spec ESC-SPEC-1, behaviour B1; SEC-01, SEC-02)."""

from __future__ import annotations

from collections.abc import Mapping

from ..models import Project, User
from ..roles import can_view_project
from .model import MAX_DELAY_MINUTES, MIN_DELAY_MINUTES, RULE_EDITORS, RULE_PRIORITIES, Rule, RuleRejected


def validate_rule(rule: Rule, editor: User, project: Project, users: Mapping[int, User]) -> Rule:
    """Return `rule` unchanged if `editor` may save it for `project`; raise RuleRejected if not.

    `users` maps every workspace user's ID to the user. Checks run in this
    order, and the first failure is raised:

    1. editor: only Owners and Admins change rules (D2)       -> not_rule_editor
    2. priority: P1 only in this release; P2 rules need business
       hours (ESC-R07), which Chapter 8 adds                 -> unsupported_priority
    3. steps: at least one                                    -> no_steps
    4. each step, in order (all of step 1, then all of step 2, ...):
       a. numbered n, for the n-th step                        -> steps_not_numbered
       b. delay: a whole number of minutes from 5 to 240       -> delay_out_of_range
       c. delay greater than the previous step's (D1)          -> delays_not_increasing
       d. at least one target (ESC-N06)                        -> no_targets
       e. each target, in order: an int user ID (ESC-N05)      -> target_not_user
          in the workspace                                     -> target_not_in_workspace
          who can view the project (ESC-R08)                   -> target_cannot_view_project

    Messages name what was refused: the allowed range for delays (ESC-AC10)
    and the user's name and role for targets (ESC-AC14). Validation is a pure
    function, so a refused rule is never partly applied.
    """
    raise NotImplementedError('validate_rule')

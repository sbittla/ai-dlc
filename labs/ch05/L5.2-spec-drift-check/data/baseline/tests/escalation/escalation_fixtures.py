"""Shared test data for the escalation slice (spec ESC-SPEC-1). Imported by the test modules.

A small workspace with two projects. Times are UTC; the P1 priority is set at
02:30 UTC on 24 November 2026.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from relay.escalation import EscalationState, Rule, Step
from relay.models import Project, Task, User

SPEC_DIR = Path(__file__).resolve().parents[2] / "specs" / "001-escalation-rules"
SCHEMA = json.loads((SPEC_DIR / "contracts" / "escalation-rules.schema.json").read_text(encoding="utf-8"))
UTC = timezone.utc
T0 = datetime(2026, 11, 24, 2, 30, tzinfo=UTC)

ROTTERDAM = Project(10, "Rotterdam")
ANTWERP = Project(11, "Antwerp")
OWNER = User(1, "anouk@customer.example", "Anouk", "Owner", "Europe/Berlin")
ADMIN = User(2, "joost@customer.example", "Joost", "Admin", "Europe/Berlin")
ADMIN_2 = User(3, "sanne@customer.example", "Sanne", "Admin", "Europe/Berlin")
MEMBER = User(4, "daan@customer.example", "Daan", "Member", "Europe/Berlin")
GUEST_INVITED = User(5, "ines@contractor.example", "Ines", "Guest", "Europe/Berlin", frozenset({10}))
GUEST_ELSEWHERE = User(6, "tom@contractor.example", "Tom", "Guest", "Europe/Berlin", frozenset({11}))
USERS = {u.id: u for u in (OWNER, ADMIN, ADMIN_2, MEMBER, GUEST_INVITED, GUEST_ELSEWHERE)}


def minutes(n: float) -> datetime:
    return T0 + timedelta(minutes=n)


def p1_rule(*delays_and_targets) -> Rule:
    """p1_rule((10, (5,)), (20, (2,))) -> a P1 rule for Rotterdam with those steps."""
    steps = tuple(Step(n, delay, tuple(targets)) for n, (delay, targets) in enumerate(delays_and_targets, 1))
    return Rule("R-ROT-P1", ROTTERDAM.id, "P1", steps)


def p1_state(**changes) -> EscalationState:
    base = dict(task_id=7, priority="P1", priority_set_at=T0)
    base.update(changes)
    return EscalationState(**base)


def default_rule() -> Rule:
    """ESC-R04's defaults: steps at 10 and 20 minutes."""
    return p1_rule((10, (GUEST_INVITED.id,)), (20, (ADMIN.id,)))


TASK = Task(7, ROTTERDAM.id, "Scanner gateway down in hall 3")

"""The rule notice (spec ESC-SPEC-1 1.2.0, B8; ESC-N06, SEC-04). Task T22.

Spec: ESC-SPEC-1
Spec version: 1.2.0

Every expected subject and body below is written out by hand from B8.
"""

import pytest
from escalation_fixtures import ADMIN, OWNER, ROTTERDAM, SCHEMA, default_rule, minutes, p1_rule, p2_rule

from relay.escalation import Rule, to_document, validate
from relay.escalation.delivery import rule_notice_email, rules_link

LINK = "https://relay.example/ws-demo/projects/10/escalation-rules"
NAMED = Rule("R-ROT-P1", ROTTERDAM.id, "P1", default_rule().steps, "Rotterdam night P1")


def test_the_rules_link_names_the_project():
    assert rules_link("https://relay.example/ws-demo/", 10) == LINK


def test_ESC_AC25_a_deletion_notice_names_the_rule_and_the_admin():
    msg = rule_notice_email("deleted", NAMED, None, ROTTERDAM, ADMIN.id, "Admin", minutes(0), LINK, OWNER.id)
    assert (msg.kind, msg.to_user) == ("rule_notice", 1)
    assert msg.subject == "[Relay] P1 escalation rule deleted in Rotterdam: Rotterdam night P1"
    assert msg.body.splitlines() == [
        "Admin user 2 deleted the escalation rule Rotterdam night P1 (R-ROT-P1) in Rotterdam",
        "at 2026-11-24 02:30 UTC.",
        "",
        "Before: P1, steps at 10 and 20 minutes, 2 target(s). Its steps no longer fire for any task.",
        "",
        "Review the project's rules: https://relay.example/ws-demo/projects/10/escalation-rules",
        "You receive this because you are the workspace's Owner or an Admin (ESC-N06).",
    ]


def test_SEC08_a_change_notice_shows_the_shape_before_and_after():
    quiet = p2_rule()  # the same rule turned into a P2 rule with business hours: one step at 240, one target
    after = Rule("R-ROT-P1", ROTTERDAM.id, "P2", quiet.steps, "Rotterdam night P1", quiet.business_hours)
    msg = rule_notice_email("changed", NAMED, after, ROTTERDAM, OWNER.id, "Owner", minutes(1), LINK, ADMIN.id)
    assert msg.subject == "[Relay] P1 escalation rule changed in Rotterdam: Rotterdam night P1"
    assert msg.body.splitlines()[:5] == [
        "Owner user 1 changed the escalation rule Rotterdam night P1 (R-ROT-P1) in Rotterdam",
        "at 2026-11-24 02:31 UTC.",
        "",
        "Before: P1, steps at 10 and 20 minutes, 2 target(s).",
        "After: P2, step at 240 business minutes, 1 target(s).",
    ]


def test_SEC04_a_notice_carries_no_user_name_or_address():
    msg = rule_notice_email("deleted", NAMED, None, ROTTERDAM, ADMIN.id, "Admin", minutes(0), LINK, OWNER.id)
    text = (msg.subject + "\n" + msg.body).lower()
    for word in ("anouk", "joost", "sanne", "@customer.example", "@"):
        assert word not in text


def test_a_notice_is_a_valid_email_message_document():
    msg = rule_notice_email("deleted", p1_rule((10, (2,))), None, ROTTERDAM, ADMIN.id, "Admin", minutes(0), LINK, 1)
    assert validate(to_document(msg), {"$ref": "#/$defs/EmailMessage"}, SCHEMA) == []


def test_only_changed_and_deleted_are_actions():
    with pytest.raises(ValueError):
        rule_notice_email("created", NAMED, None, ROTTERDAM, ADMIN.id, "Admin", minutes(0), LINK, OWNER.id)

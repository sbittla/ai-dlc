"""Messages for delivery (B5), written test-first from the spec and approved before delivery.py existed.

Spec: ESC-SPEC-1
Spec version: 1.1.0

The oracles are independent of the code under test: the signature is
recomputed with the standard library's hmac, the title's parts are the
criterion's own words, and every expected string is copied from the spec.
"""

import hashlib
import hmac
import json
import re

from escalation_fixtures import ADMIN, GUEST_INVITED, OWNER, ROTTERDAM, USERS, minutes, p1_rule

from relay.escalation import EngineConfig, EscalationStore, Webhook, run_pass, save_rule, set_priority
from relay.models import Task

SECRET = b"whsec-test-only-0001"
LINK = "https://relay.example/ws-demo/projects/10/tasks/7"
TITLED = Task(7, ROTTERDAM.id, "Customer 4471 card data exposed")


def fire(rule, at_minutes, webhook=True):
    """Save `rule`, have a person set P1 at minute 0, run one pass at `at_minutes`; return the outbox."""
    store = EscalationStore()
    save_rule(store, rule, ADMIN, ROTTERDAM, USERS, minutes(-60))
    set_priority(store, TITLED, ROTTERDAM, OWNER, "P1", minutes(0))
    hook = Webhook("https://hooks.customer.example/relay", SECRET) if webhook else None
    run_pass(store, {TITLED.id: TITLED}, {ROTTERDAM.id: ROTTERDAM}, EngineConfig("https://relay.example/ws-demo", hook),
             minutes(at_minutes))
    return store.outbox()


def two_target_rule():
    rule = p1_rule((10, (GUEST_INVITED.id, ADMIN.id)), (20, (ADMIN.id,)))
    return type(rule)(rule.rule_id, rule.project_id, rule.priority, rule.steps, "Rotterdam night P1")


def emails(outbox):
    return [json.loads(item.body) for item in outbox if item.channel == "email"]


def events(outbox):
    return [item for item in outbox if item.channel == "webhook"]


def test_ESC_AC15_two_targets_get_two_emails_and_one_signed_event():
    outbox = fire(two_target_rule(), 10)
    assert sorted(e["to_user"] for e in emails(outbox)) == [ADMIN.id, GUEST_INVITED.id]
    [event] = events(outbox)
    assert json.loads(event.body)["event"] == "task.escalated"
    expected = "sha256=" + hmac.new(SECRET, event.body.encode("utf-8"), hashlib.sha256).hexdigest()
    assert event.headers["X-Relay-Signature"] == expected


def test_ESC_AC15_the_signed_bytes_are_the_bytes_sent():
    [event] = events(fire(two_target_rule(), 10))
    body = event.body.encode("utf-8")
    assert body == json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8")


def test_ESC_AC15_no_webhook_configured_means_no_event():
    outbox = fire(two_target_rule(), 10, webhook=False)
    assert len(emails(outbox)) == 2 and events(outbox) == []


def test_ESC_AC17_email_shows_rule_name_step_and_both_times_in_utc():
    [email] = [e for e in emails(fire(two_target_rule(), 10)) if e["to_user"] == GUEST_INVITED.id]
    text = email["subject"] + "\n" + email["body"]
    assert "Rotterdam night P1" in text
    assert "Step: 1" in email["body"]
    assert "Delay started: 2026-11-24 02:30 UTC" in email["body"]
    assert "Step fired: 2026-11-24 02:40 UTC" in email["body"]


def test_ESC_AC27_no_part_of_the_title_in_emails_or_the_webhook_and_both_carry_the_link():
    outbox = fire(two_target_rule(), 10)
    parts = {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", TITLED.title)}
    assert parts == {"customer", "4471", "card", "data", "exposed"}
    payloads = [e["subject"] + "\n" + e["body"] for e in emails(outbox)] + [e.body for e in events(outbox)]
    assert len(payloads) == 3
    for payload in payloads:
        words = {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", payload.replace(LINK, " "))}
        assert words & parts == set(), payload
        assert LINK in payload


def test_ESC_AC27_the_link_is_the_only_place_the_task_id_appears_in_the_subject():
    for email in emails(fire(two_target_rule(), 10)):
        assert "4471" not in email["subject"] and "\n" not in email["subject"]


def test_messages_carry_user_ids_not_addresses():
    outbox = fire(two_target_rule(), 10)
    text = json.dumps([item.__dict__ for item in outbox], default=str)
    assert not re.search(r"[\w.-]+@[\w.-]+", text)

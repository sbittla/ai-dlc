"""The email delivery adapter (4.26.0, ADR-033): every kind accepted, recipients only from the directory.

Messages are built with the engine's own message functions and written to a real outbox, so the adapter
reads exactly what the engine writes. Expected outcomes are worked out by hand from ADR-033's check order.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from relay.delivery import ACCEPTED_KINDS, EmailAdapter, RecordingTransport
from relay.escalation import EscalationStore, Rule, Step, StepDecision, run_pass, save_rule, set_priority
from relay.escalation.contract import to_document
from relay.escalation.delivery import escalation_email, rule_notice_email, rules_link, summary_email, task_link
from relay.escalation.model import EMAIL_KINDS
from relay.models import Project, Task, User
from relay.notify import NotifyStore, Prefs

UTC = timezone.utc
T0 = datetime(2027, 2, 9, 2, 30, tzinfo=UTC)
BASE = "https://relay.example/ws-demo"
PROJECT = Project(10, "Rotterdam")
OWNER = User(1, "anouk@customer.example", "Anouk", "Owner", "Europe/Berlin")
ADMIN = User(2, "joost@customer.example", "Joost", "Admin", "Europe/Berlin")
USERS = {u.id: u for u in (OWNER, ADMIN)}
ADDRESSES = {1: "anouk@customer.example", 2: "joost@customer.example"}
RULE = Rule("R-ROT-P1", PROJECT.id, "P1", (Step(1, 10, (2,)),), "Rotterdam night P1")


def outbox_with(*messages):
    store = EscalationStore()
    for n, message in enumerate(messages):
        store.add_outbox(f"k{n}", T0, "email", message.kind, str(message.to_user), {},
                         json.dumps(to_document(message), sort_keys=True))
    return store


def adapter(store, prefs=None, transport=None):
    return EmailAdapter(store, ADDRESSES, prefs or (lambda uid: Prefs()), transport or RecordingTransport(),
                        "relay@relay.example", BASE)


def escalation(to_user=2, link=f"{BASE}/projects/10/tasks/7"):
    return escalation_email(StepDecision(1, (to_user,), T0), to_user, RULE, PROJECT, 7, link, T0, T0)


def test_the_adapter_accepts_every_email_kind_the_contract_lists():
    assert ACCEPTED_KINDS == EMAIL_KINDS


def test_each_kind_is_sent_once_to_the_directory_address():
    notice = rule_notice_email("deleted", RULE, None, PROJECT, 2, "Admin", T0, rules_link(BASE, 10), 1)
    summary = summary_email(2, [(7, task_link(BASE, 10, 7), "Rotterdam night P1", 1)], T0)
    store = outbox_with(escalation(), notice, summary)
    t = RecordingTransport()
    a = adapter(store, transport=t)
    assert [d.status for d in a.deliver(T0)] == ["sent", "sent", "sent"]
    assert [m["to"] for m in t.sent] == ["joost@customer.example", "anouk@customer.example",
                                        "joost@customer.example"]
    assert a.deliver(T0 + timedelta(minutes=1)) == []  # nothing is sent twice
    assert len(t.sent) == 3


def test_ESC_R10_a_spam_mark_suppresses_the_email_and_the_outcome_is_recorded():
    notify = NotifyStore()
    notify.mark_spam(2, date(2027, 2, 1))
    a = adapter(outbox_with(escalation()), prefs=notify.prefs)
    [d] = a.deliver(T0)
    assert (d.status, d.reason) == ("suppressed", "spam_mark")
    assert a.log()[0]["status"] == "suppressed"


def test_a_muted_type_never_silences_a_page_but_a_digest_mute_holds_the_hourly_summary():
    notify = NotifyStore()
    notify.set_muted(2, ["all"])
    summary = summary_email(2, [(7, task_link(BASE, 10, 7), "Rotterdam night P1", 1)], T0)
    out = adapter(outbox_with(escalation(), summary), prefs=notify.prefs).deliver(T0)
    assert [(d.kind, d.status, d.reason) for d in out] == [("escalation", "sent", None),
                                                          ("summary", "suppressed", "muted_all")]


def test_a_user_without_a_directory_address_is_refused_not_sent_elsewhere():
    t = RecordingTransport()
    [d] = adapter(outbox_with(escalation(to_user=9)), transport=t).deliver(T0)
    assert (d.status, d.reason) == ("refused", "no_address") and t.sent == []


def test_a_link_outside_relay_is_refused_as_a_row_the_engine_did_not_write():
    t = RecordingTransport()
    forged = escalation(link="https://collector.attacker.example/?d=customer-list")
    [d] = adapter(outbox_with(forged), transport=t).deliver(T0)
    assert (d.status, d.reason) == ("refused", "foreign_link") and t.sent == []


@pytest.mark.parametrize("link", ["HTTPS://sink.attacker.example/c", "//sink.attacker.example/c",
                                  "www.sink.attacker.example/c", "ftp://sink.attacker.example/c",
                                  "HTTPS://RELAY.EXAMPLE/ws-demo/projects/10/tasks/7"])
def test_every_address_shape_outside_relay_is_refused(link):
    t = RecordingTransport()
    [d] = adapter(outbox_with(escalation(link=link)), transport=t).deliver(T0)
    assert (d.status, d.reason) == ("refused", "foreign_link") and t.sent == []


def test_a_row_whose_message_names_another_user_or_kind_is_refused():
    store = EscalationStore()
    store.add_outbox("k1", T0, "email", "escalation", "1", {},
                     json.dumps(to_document(escalation(to_user=2)), sort_keys=True))
    store.add_outbox("k2", T0, "email", "marketing", "2", {}, "{}")
    out = adapter(store).deliver(T0)
    assert [(d.status, d.reason) for d in out] == [("refused", "mismatch"), ("refused", "unknown_kind")]


def test_provider_errors_are_retried_then_recorded_as_failed():
    t = RecordingTransport(fail_times=5)
    a = adapter(outbox_with(escalation()), transport=t)
    assert [a.deliver(T0)[0].status for _ in range(3)] == ["retry", "retry", "failed"]
    assert a.deliver(T0) == [] and a.log()[0]["attempts"] == 3


def test_end_to_end_the_engine_writes_and_the_adapter_sends():
    store = EscalationStore()
    task = Task(7, PROJECT.id, "Customer 4471 card data exposed")
    save_rule(store, RULE, ADMIN, PROJECT, USERS, T0 - timedelta(hours=1))
    set_priority(store, task, PROJECT, OWNER, "P1", T0)
    from relay.escalation import EngineConfig
    run_pass(store, {7: task}, {10: PROJECT}, EngineConfig(BASE, None), T0 + timedelta(minutes=10))
    t = RecordingTransport()
    out = adapter(store, transport=t).deliver(T0 + timedelta(minutes=11))
    assert [d.kind for d in out if d.status == "sent"] == ["escalation"]
    assert "card data" not in t.sent[0]["body"] and f"{BASE}/projects/10/tasks/7" in t.sent[0]["body"]


def test_link_base_must_be_https():
    with pytest.raises(ValueError):
        EmailAdapter(EscalationStore(), ADDRESSES, lambda uid: Prefs(), RecordingTransport(), "r@x", "http://x")

"""Deleting rules, and notices for P1 rule changes (spec ESC-SPEC-1 1.2.0, B8; ESC-AC25, SEC-08). Task T23.

Spec: ESC-SPEC-1
Spec version: 1.2.0

The workspace in escalation_fixtures has one Owner (1) and two Admins (2, 3),
as ESC-AC25 requires, so every P1 notice goes to exactly users 1, 2 and 3.
"""

import json

import pytest
from escalation_fixtures import (ADMIN, ADMIN_2, MEMBER, OWNER, ROTTERDAM, TASK, USERS, ANTWERP, default_rule,
                                 minutes, p1_rule, p2_rule)

from relay.escalation import (EngineConfig, EscalationStore, Rule, RuleIdInUse, RuleNotFound, RuleRejected,
                              delete_rule, engine, notice_recipients, rules_for, run_pass, save_rule, set_priority)

BASE = "https://relay.example/ws-demo"
CONFIG = EngineConfig(BASE)


def saved(rule=None):
    store = EscalationStore()
    save_rule(store, rule or default_rule(), ADMIN, ROTTERDAM, USERS, minutes(-60), BASE)
    return store


def notices(store):
    return [(item.created_at, json.loads(item.body)) for item in store.outbox() if item.kind == "rule_notice"]


def test_the_owner_and_every_admin_receive_notices():
    assert notice_recipients(USERS) == [OWNER.id, ADMIN.id, ADMIN_2.id]


def test_ESC_AC25_an_admin_deletes_a_p1_rule_and_the_owner_and_both_admins_get_an_email_naming_both():
    store = saved()
    delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(0), BASE)
    sent = notices(store)
    assert [body["to_user"] for _at, body in sent] == [1, 2, 3]
    for at, body in sent:
        assert at == minutes(0)  # committed with the deletion, so well within 5 minutes
        assert "R-ROT-P1" in body["subject"] + body["body"]
        assert body["body"].startswith("Admin user 2 deleted the escalation rule R-ROT-P1 in Rotterdam")


def test_a_deleted_rule_stops_firing_at_once():
    store = saved()
    set_priority(store, TASK, ROTTERDAM, MEMBER, "P1", minutes(0))
    delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(5), BASE)
    assert run_pass(store, {TASK.id: TASK}, {ROTTERDAM.id: ROTTERDAM}, CONFIG, minutes(25)).steps_fired == 0
    assert rules_for(store, ROTTERDAM.id) == []


def test_a_deletion_is_audited_with_the_rule_before_and_nothing_after():
    store = saved()
    delete_rule(store, "R-ROT-P1", ADMIN_2, ROTTERDAM, USERS, minutes(0), BASE)
    entry = store.audit("R-ROT-P1")[-1]
    assert (entry.outcome, entry.actor_id, entry.at, entry.after) == ("deleted", ADMIN_2.id, minutes(0), None)
    assert [s["delay_minutes"] for s in entry.before["steps"]] == [10, 20]


def test_a_member_is_refused_audited_and_the_rule_is_unchanged():
    store = saved()
    with pytest.raises(RuleRejected) as info:
        delete_rule(store, "R-ROT-P1", MEMBER, ROTTERDAM, USERS, minutes(0), BASE)
    assert info.value.code == "not_rule_editor"
    assert rules_for(store, ROTTERDAM.id) == [default_rule()]
    assert (store.audit()[-1].outcome, store.audit()[-1].code) == ("refused", "not_rule_editor")
    assert notices(store) == []


@pytest.mark.parametrize("rule_id, project", [("R-NONE", ROTTERDAM), ("R-ROT-P1", ANTWERP)])
def test_an_unknown_rule_or_another_projects_rule_is_not_found(rule_id, project):
    with pytest.raises(RuleNotFound):
        delete_rule(saved(), rule_id, ADMIN, project, USERS, minutes(0), BASE)


def test_deleting_twice_is_not_found_and_sends_no_second_notice():
    store = saved()
    delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(0), BASE)
    with pytest.raises(RuleNotFound):
        delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(1), BASE)
    assert len(notices(store)) == 3


def test_deleting_a_p2_rule_is_audited_and_sends_no_notice():
    store = saved(p2_rule())
    delete_rule(store, "R-ROT-P2", ADMIN, ROTTERDAM, USERS, minutes(0), BASE)
    assert store.audit("R-ROT-P2")[-1].outcome == "deleted" and notices(store) == []


def test_a_deleted_rules_id_is_never_reused():
    store = saved()
    delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(0), BASE)
    with pytest.raises(RuleIdInUse):
        save_rule(store, default_rule(), ADMIN, ROTTERDAM, USERS, minutes(1), BASE)
    assert (store.audit()[-1].outcome, store.audit()[-1].code) == ("refused", "rule_id_deleted")


def test_SEC08_changing_a_p1_rule_to_p4_is_a_p1_change_and_is_loud():
    store = saved()
    p4 = Rule("R-ROT-P1", ROTTERDAM.id, "P4", (p2_rule().steps[0],), None, p2_rule().business_hours)
    save_rule(store, p4, ADMIN, ROTTERDAM, USERS, minutes(1), BASE)
    sent = notices(store)
    assert [body["to_user"] for _at, body in sent] == [1, 2, 3]
    assert "After: P4, step at 240 business minutes, 1 target(s)." in sent[0][1]["body"]


def test_SEC08_replacing_a_p1_rule_notifies_but_creating_one_does_not():
    store = saved()
    assert notices(store) == []  # creation cannot silence an escalation (spec 1.2.0, Terms)
    save_rule(store, p1_rule((15, (5,)), (20, (2,))), ADMIN, ROTTERDAM, USERS, minutes(1), BASE)
    assert len(notices(store)) == 3


def test_SEC08_a_deletion_cannot_commit_without_its_notices(monkeypatch):
    store = saved()

    def broken(*args, **kwargs):
        raise RuntimeError("the notice could not be written")

    monkeypatch.setattr(engine, "rule_notice_email", broken)
    with pytest.raises(RuntimeError):
        delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(0), BASE)
    assert rules_for(store, ROTTERDAM.id) == [default_rule()]
    assert [e.outcome for e in store.audit("R-ROT-P1")] == ["saved"]


def test_a_held_email_for_a_deleted_rule_still_links_to_its_project():
    """Found by impact analysis: the hour's summary looked rules up by ID and, for a missing one, linked project 0."""
    store = saved()
    store.hold(ADMIN.id, TASK.id, "R-ROT-P1", 1, minutes(0), minutes(30))
    delete_rule(store, "R-ROT-P1", ADMIN, ROTTERDAM, USERS, minutes(1), BASE)
    run_pass(store, {}, {}, CONFIG, minutes(30))
    [summary] = [json.loads(i.body) for i in store.outbox() if i.kind == "summary"]
    assert f"{BASE}/projects/10/tasks/{TASK.id}" in summary["body"]

"""Approval gates (4.24.0, ADR-026): authenticated people only, the right person, exact arguments, expiry, audit."""

import pytest

from agents_helpers import PERSON_ISSUER, PR_ARGS, World
from relay.agents import ApprovalRefused, apply_budget_raise, request_budget_raise

ARGS = dict(PR_ARGS, diff_sha256="a" * 64)


def ask(w, rule="requester", requested_for="priya.n", args=ARGS, tool="open_pull_request"):
    return w.gate.request(w.run_id, tool, args, rule, "spec-to-pr-helper", requested_for)


def test_a_request_is_recorded_once_per_exact_call():
    w = World()
    a, b = ask(w), ask(w)
    assert a.approval_id == b.approval_id and a.status == "pending"
    assert w.gate.find(w.run_id, "open_pull_request", dict(ARGS, diff_sha256="b" * 64)) is None


def test_the_decider_is_authenticated_by_a_fresh_person_proof():
    w = World()
    a = ask(w)
    stale = dict(w.person("priya.n"), iat=w.clock() - 301)
    for proof in (stale, dict(w.person("priya.n"), iss="https://evil.example"), dict(w.person("priya.n"), aud="x"),
                  {"sub": "priya.n"}):
        with pytest.raises(ApprovalRefused) as exc:
            w.gate.decide(a.approval_id, proof, True, "")
        assert exc.value.code == "bad_person_proof"
    with pytest.raises(ApprovalRefused) as exc:
        w.gate.decide(a.approval_id, w.person("spec-to-pr-helper"), True, "an agent")
    assert exc.value.code == "not_a_person"
    assert w.gate.decide(a.approval_id, w.person("priya.n"), True, "diff read").decided_by == "priya.n"


def test_only_the_requester_may_approve_a_requester_gate():
    w = World()
    a = ask(w)
    with pytest.raises(ApprovalRefused) as exc:
        w.gate.decide(a.approval_id, w.person("sam.o"), True, "looks fine to me")
    assert exc.value.code == "not_the_requester"


def test_another_person_rule_refuses_the_requester_and_needs_a_requester():
    w = World()
    a = ask(w, "another_person", args={"max_usd": 10.0}, tool="raise_budget")
    with pytest.raises(ApprovalRefused) as exc:
        w.gate.decide(a.approval_id, w.person("priya.n"), True, "I need it")
    assert exc.value.code == "requester_may_not_approve"
    assert w.gate.decide(a.approval_id, w.person("sam.o"), False, "find out why first").status == "denied"
    b = ask(w, "another_person", requested_for=None, args={"max_usd": 11.0}, tool="raise_budget")
    with pytest.raises(ApprovalRefused) as exc:
        w.gate.decide(b.approval_id, w.person("sam.o"), True, "")
    assert exc.value.code == "requester_unknown"


def test_a_decision_is_final():
    w = World()
    a = ask(w)
    w.gate.decide(a.approval_id, w.person("priya.n"), False, "wrong branch")
    with pytest.raises(ApprovalRefused) as exc:
        w.gate.decide(a.approval_id, w.person("priya.n"), True, "changed my mind")
    assert exc.value.code == "not_pending"


def test_an_undecided_request_expires_after_24_hours_and_can_be_asked_again():
    w = World()
    a = ask(w)
    w.clock.t += 24 * 3600
    with pytest.raises(ApprovalRefused) as exc:
        w.gate.decide(a.approval_id, w.person("priya.n"), True, "late")
    assert exc.value.code == "expired"
    again = ask(w)
    assert again.approval_id == a.approval_id and again.status == "pending"
    assert w.gate.decide(again.approval_id, w.person("priya.n"), True, "read it now").status == "approved"
    assert [r["action"] for r in w.trail.records].count("approval.request") == 2


def test_requests_and_decisions_are_in_the_audit_trail():
    w = World()
    a = w.gate.request(w.run_id, "open_pull_request", ARGS, "requester", "spec-to-pr-helper", "priya.n",
                       bound={"diff_sha256": "a" * 64})
    w.gate.decide(a.approval_id, w.person("priya.n"), True, "diff read")
    actions = [(r["action"], r["outcome"]) for r in w.trail.records]
    assert actions == [("approval.request", "pending"), ("approval.decide", "approved")]
    assert w.trail.records[0]["detail"]["bound"] == {"diff_sha256": "a" * 64}
    assert w.trail.records[1]["detail"]["decided_by"] == "priya.n"
    assert PERSON_ISSUER == w.gate.person_issuer


def test_a_budget_raise_is_stored_in_the_run_only_once_another_person_approved_it():
    w = World()
    new = {"max_steps": 50, "max_usd": 10.0, "max_seconds": 1800}
    with pytest.raises(ApprovalRefused):
        apply_budget_raise(w.gate, w.run_id, new)
    a = request_budget_raise(w.gate, w.run_id, new, "spec-to-pr-helper", "priya.n")
    with pytest.raises(ApprovalRefused):
        apply_budget_raise(w.gate, w.run_id, new)  # still pending
    w.gate.decide(a.approval_id, w.person("sam.o"), True, "the task is bigger than planned")
    assert apply_budget_raise(w.gate, w.run_id, new) == new
    assert w.store.run(w.run_id)["budget"] == new
    assert w.trail.records[-1]["action"] == "budget.raise"
    with pytest.raises(ApprovalRefused):
        apply_budget_raise(w.gate, w.run_id, dict(new, max_usd=99.0))  # not the raise that was approved

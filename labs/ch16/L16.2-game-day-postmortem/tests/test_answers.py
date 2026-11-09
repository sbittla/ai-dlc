"""Locks the outcomes in book/answers/ch16-answers.md (Exercise 7): the 2 February rollback through the gate."""

from datetime import datetime, timezone

import pytest

from gameday import DATA
from gameday.remediate import Gate, Refused, args_sha256, make_proof
from gameday.replay import incident, judge
from gameday.store import load_json

UTC = timezone.utc
PEOPLE = load_json(DATA / "people.json")
V0 = load_json(DATA / "incident-2027-02-02" / "assistant-v0.json")
DEPLOY = datetime(2027, 2, 2, 15, 0, tzinfo=UTC)
ARGS = {"deploy": "deploy-2027-02-02"}
SHA = args_sha256(ARGS)


def at(h, m, s=0):
    return datetime(2027, 2, 2, h, m, s, tzinfo=UTC)


def verdicts_at(t):
    return {v.hypothesis: v.status for v in judge(V0, incident()["store"], t)}


def proof(who, t, **bind):
    return make_proof(PEOPLE, who, t, **bind)


def test_exercise_7_the_assistants_rollback_is_refused_because_h0_is_unsupported():
    verdicts = verdicts_at(at(15, 22))
    assert verdicts == {"H0": "unsupported"}
    gate = Gate(PEOPLE, deploys=[DEPLOY])
    with pytest.raises(Refused) as exc:
        gate.request("deploy.rollback", ARGS, proof("incident-assistant", at(15, 22), purpose="request",
                                                    action="deploy.rollback", args_sha256=SHA),
                     at(15, 22), because="H0", verdicts=verdicts)
    assert exc.value.code == "unsupported_hypothesis" and gate.audit[-1]["by"] == "incident-assistant"


def test_exercise_7_a_person_may_override_in_writing_and_two_fresh_proofs_approve():
    verdicts = verdicts_at(at(15, 22))
    gate = Gate(PEOPLE, deploys=[DEPLOY])
    with pytest.raises(Refused) as exc:
        gate.request("deploy.rollback", ARGS, proof("priya.n", at(15, 22), purpose="request",
                                                    action="deploy.rollback", args_sha256=SHA),
                     at(15, 22), because="H0", verdicts=verdicts)
    assert exc.value.code == "override_reason_required"
    req = gate.request("deploy.rollback", ARGS, proof("priya.n", at(15, 22, 5), purpose="request",
                                                      action="deploy.rollback", args_sha256=SHA),
                       at(15, 22, 5), because="H0", verdicts=verdicts, override="the deploy came first")
    assert [a["outcome"] for a in gate.audit[-2:]] == ["override", "requested"]
    rid = req.request_id
    gate.decide(rid, proof("priya.n", at(15, 22, 10), purpose="decide", request_id=rid, args_sha256=SHA),
                True, at(15, 22, 20))
    stale = proof("sam.o", at(15, 16), purpose="decide", request_id=rid, args_sha256=SHA)
    with pytest.raises(Refused) as exc:
        gate.decide(rid, stale, True, at(15, 22, 40))
    assert exc.value.code == "stale_proof"
    fresh = proof("sam.o", at(15, 22, 30), purpose="decide", request_id=rid, args_sha256=SHA)
    assert gate.decide(rid, fresh, True, at(15, 22, 40)).status == "approved"

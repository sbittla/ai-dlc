"""Locks the outcomes in book/answers/ch16-answers.md (Exercise 7): the 2 February rollback through the gate."""

from datetime import datetime, timezone

import pytest

from gameday import DATA
from gameday.remediate import Gate, Refused, args_sha256, make_proof
from gameday.replay import incident
from gameday.store import load_json

UTC = timezone.utc
PEOPLE = load_json(DATA / "people.json")
V0 = load_json(DATA / "incident-2027-02-02" / "assistant-v0.json")
V1 = load_json(DATA / "incident-2027-02-02" / "assistant-v1.json")
DEPLOY = datetime(2027, 2, 2, 15, 0, tzinfo=UTC)
ARGS = {"deploy": "deploy-2027-02-02"}
SHA = args_sha256(ARGS)
STORE = incident()["store"]


def at(h, m, s=0):
    return datetime(2027, 2, 2, h, m, s, tzinfo=UTC)


def gate(assistant=V0):
    return Gate(PEOPLE, deploys=[DEPLOY], store=STORE, hypotheses={h["id"]: h for h in assistant["hypotheses"]})


def request(g, who, t, because, override=""):
    proof = make_proof(PEOPLE, who, t, purpose="request", action="deploy.rollback", args_sha256=SHA)
    return g.request("deploy.rollback", ARGS, proof, t, because=because, override=override)


def code(fn, *a, **kw):
    with pytest.raises(Refused) as exc:
        fn(*a, **kw)
    return exc.value.code


def test_exercise_7_the_assistants_rollback_is_refused():
    g = gate()
    assert g.verdict("H0", at(15, 22))[1] == "unsupported"
    assert code(request, g, "incident-assistant", at(15, 22), "H0") == "unsupported_hypothesis"
    # Citing v1's supported sign-in hypotheses instead does not help: they are not about the deploy.
    g1 = gate(V1)
    assert code(request, g1, "incident-assistant", at(15, 22, 1), "H2") == "hypothesis_does_not_match_action"
    assert code(request, g1, "incident-assistant", at(15, 22, 2), "H3") == "hypothesis_does_not_match_action"


def test_exercise_7_a_person_may_override_with_an_incident_id_and_two_fresh_proofs_approve():
    g = gate()
    assert code(request, g, "priya.n", at(15, 22), "H0") == "override_reason_required"
    assert code(request, g, "priya.n", at(15, 22, 1), "H0", override="the deploy came first") == \
        "override_reason_required"
    req = request(g, "priya.n", at(15, 22, 5), "H0", override="INC-0202: the deploy came first, so roll it back")
    assert [a["outcome"] for a in g.audit[-2:]] == ["override", "requested"]
    rid = req.request_id
    g.decide(rid, make_proof(PEOPLE, "priya.n", at(15, 22, 10), purpose="decide", request_id=rid, args_sha256=SHA),
             True, at(15, 22, 20))
    stale = make_proof(PEOPLE, "sam.o", at(15, 16), purpose="decide", request_id=rid, args_sha256=SHA)
    assert code(g.decide, rid, stale, True, at(15, 22, 40)) == "stale_proof"
    fresh = make_proof(PEOPLE, "sam.o", at(15, 22, 30), purpose="decide", request_id=rid, args_sha256=SHA)
    assert g.decide(rid, fresh, True, at(15, 22, 40)).status == "approved"

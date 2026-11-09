"""Hand-checkable fixtures for TODO 1 to TODO 4. Each expected value is worked out in the comment beside it."""

from datetime import datetime, timedelta, timezone

import pytest

from gameday.citations import FAILS, HOLDS, UNBOUND, UNRESOLVED, check_citation, check_hypothesis
from gameday.postmortem import check
from gameday.remediate import Gate, Refused, args_sha256, make_proof
from gameday.store import Store
from gameday.timeline import Entry, fault_measures

UTC = timezone.utc
DAY = datetime(2027, 3, 1, tzinfo=UTC)


def store(as_of=None):
    # Ten minutes 10:00-10:09. Load is 10 until 10:05, then 100. Slow share 0.01, then 0.5 from 10:06.
    rows = []
    for m in range(10):
        rows.append({"minute": f"2027-03-01T10:{m:02d}Z", "load": 10.0 if m < 5 else 100.0,
                     "api_requests": 100.0, "api_slow": 1.0 if m < 6 else 50.0, "share_db_of_request": 0.8})
    events = [{"id": "change", "at": "2027-03-01T10:02:00Z"},
              {"id": "undo", "at": "2027-03-01T10:03:00Z", "done": "2027-03-01T10:03:00Z", "removes": "change"}]
    return Store(DAY, rows, events, [], as_of=as_of, baseline=("10:00", "10:01"),
                 mechanisms={"metric:load": "share:db_of_request", "event:change": "share:db_of_request"})


# ---------------------------------------------------------------- TODO 1a

@pytest.mark.parametrize("citation,expected", [
    ({"ref": "event:change", "assert": "exists"}, HOLDS),
    ({"ref": "event:nothing", "assert": "exists"}, UNRESOLVED),
    ({"ref": "metric:load", "assert": "rises", "window": ["10:05", "10:09"], "baseline": ["10:00", "10:04"],
      "factor": 10}, HOLDS),                                   # 100 >= 10 x 10
    ({"ref": "metric:load", "assert": "rises", "window": ["10:05", "10:09"], "baseline": ["10:00", "10:04"],
      "factor": 11}, FAILS),
    ({"ref": "share:db_of_request", "assert": "dominates", "window": ["10:00", "10:09"], "share": 0.8}, HOLDS),
    ({"ref": "share:db_of_request", "assert": "dominates", "window": ["10:00", "10:09"], "share": 0.81}, FAILS),
    # Load's onset (10 x 10 = 100, after the baseline 10:00-10:01) is 10:05; slow share's (5 x 0.01) is 10:06.
    ({"ref": "metric:load", "assert": "precedes", "effect": "metric:api_slow_share", "baseline": ["10:00", "10:01"],
      "factor": 5}, HOLDS),
    ({"ref": "metric:api_slow_share", "assert": "precedes", "effect": "metric:load", "baseline": ["10:00", "10:01"],
      "factor": 5}, FAILS),
    ({"ref": "event:change", "assert": "precedes", "effect": "metric:api_slow_share", "baseline": ["10:00", "10:01"],
      "factor": 5}, HOLDS),                                   # 10:02 is before 10:06
])
def test_todo1a_citations(citation, expected):
    assert check_citation(citation, store()) == expected


def test_todo1a_nothing_after_as_of_is_visible():
    early = store(as_of=DAY.replace(hour=10, minute=4))
    rises = {"ref": "metric:load", "assert": "rises", "window": ["10:05", "10:09"], "baseline": ["10:00", "10:04"],
             "factor": 10}
    assert check_citation(rises, early) == UNRESOLVED  # the window has not happened yet


# ---------------------------------------------------------------- TODO 1b

def cause(cites, cause_ref="metric:load"):
    return {"id": "H", "kind": "cause", "cause": cause_ref, "effect": "metric:api_slow_share", "citations": cites}


RISES = {"ref": "metric:load", "assert": "rises", "window": ["10:05", "10:09"], "baseline": ["10:00", "10:04"],
         "factor": 10}
DOMINATES = {"ref": "share:db_of_request", "assert": "dominates", "window": ["10:05", "10:09"], "share": 0.5}


def test_todo1b_supported_needs_timing_and_a_mechanism():
    assert check_hypothesis(cause([RISES, DOMINATES]), store()).status == "supported"
    v = check_hypothesis(cause([RISES]), store())
    assert (v.status, v.reason) == ("unsupported", "no mechanism cited")
    v = check_hypothesis(cause([DOMINATES]), store())
    assert (v.status, v.reason) == ("unsupported", "no timing cited")
    v = check_hypothesis(cause([{**RISES, "factor": 11}, DOMINATES]), store())
    assert (v.status, v.reason, v.results) == ("unsupported", "citation 1 fails", (FAILS, HOLDS))


def test_todo1b_a_citation_about_another_signal_supports_nothing():
    # Cross-wired (round 1's probe): the cited rise and mechanism belong to a different cause.
    s = store()
    s.mechanisms["metric:api_requests"] = "share:other"
    v = check_hypothesis(cause([RISES, DOMINATES], cause_ref="metric:api_requests"), s)
    assert (v.status, v.results) == ("unsupported", (UNBOUND, UNBOUND))


def test_todo1b_no_citations_and_a_relabelled_kind_are_not_supported():
    assert check_hypothesis({"id": "E", "citations": []}, store()).reason == "no citations"
    relabelled = {"id": "R", "kind": "attribution", "cause": "metric:load", "effect": "metric:api_slow_share",
                  "citations": [{"ref": "event:change", "assert": "exists"}]}
    v = check_hypothesis(relabelled, store())
    assert (v.status, v.reason) == ("unsupported", "no mechanism cited")


def test_todo1b_the_checker_owns_the_baseline():
    # A model-chosen baseline inside the surge (10:05-10:09) would hide the rise; the checker ignores it.
    assert check_citation({**RISES, "baseline": ["10:05", "10:09"]}, store()) == HOLDS


def test_todo1b_an_effect_that_outlives_the_undone_change_contradicts_it():
    precedes = {"ref": "event:change", "assert": "precedes", "effect": "metric:api_slow_share",
                "baseline": ["10:00", "10:01"], "factor": 5}
    v = check_hypothesis(cause([precedes, DOMINATES], cause_ref="event:change"), store())
    assert v.status == "contradicted" and "after event:change was undone at 10:03" in v.reason


def test_todo1b_attribution_needs_only_its_citations():
    h = {"id": "A", "kind": "attribution", "citations": [{"ref": "event:change", "assert": "exists"}]}
    assert check_hypothesis(h, store()).status == "supported"


# ---------------------------------------------------------------- TODO 2

def test_todo2_fault_measures():
    t = lambda m: DAY.replace(hour=10) + timedelta(minutes=m)  # noqa: E731
    entries = [Entry(t(3), "alert", "A1"), Entry(t(5), "alert", "A2"), Entry(t(5), "page", "A2"),
               Entry(t(4), "ack", "A2"), Entry(t(7.5), "ack", "A1"), Entry(t(12), "action", "fix"),
               Entry(t(20), "action", "fix")]
    plan = {"faults": [{"id": "F", "start": "2027-03-01T10:00:00Z"}, {"id": "G", "start": "2027-03-01T10:00:00Z"}],
            "alerts": {"F": ["A1", "A2"], "G": ["Z"]}, "mitigations": {"F": "fix", "G": "other"}}
    assert fault_measures(entries, plan) == {
        "F": {"first_alert": "A1", "detect_min": 3.0, "first_page": "A2", "ack_min": 2.5, "mitigate_min": 12.0},
        "G": {"first_alert": None, "detect_min": None, "first_page": None, "ack_min": None, "mitigate_min": None}}


# ---------------------------------------------------------------- TODO 3

PEOPLE = {"issuer": "https://people.example", "audience": "relay-remediation", "key_hex": "11" * 32,
          "people": {"ana": ["platform-oncall"], "ben": ["tech-lead"], "cy": ["support"]},
          "agents": ["incident-assistant"]}
AT = DAY.replace(hour=12)
VERDICTS = {"H1": "supported", "H0": "unsupported"}


def req_proof(who, action, args, age_s=10, people=PEOPLE):
    return make_proof(people, who, AT - timedelta(seconds=age_s), purpose="request", action=action,
                      args_sha256=args_sha256(args))


def dec_proof(who, req, age_s=10, args=None):
    sha = args_sha256(args) if args is not None else req.args_sha256
    return make_proof(PEOPLE, who, AT - timedelta(seconds=age_s), purpose="decide", request_id=req.request_id,
                      args_sha256=sha)


def request(gate, who, action="db.failover", args=None, because="H1", age_s=10, **kw):
    args = {"cluster": "x"} if args is None else args
    return gate.request(action, args, req_proof(who, action, args, age_s), AT, because=because, verdicts=VERDICTS,
                        **kw)


def refused(fn, *a, **kw):
    with pytest.raises(Refused) as exc:
        fn(*a, **kw)
    return exc.value.code


def test_todo3_two_people_cover_the_roles_and_the_requester_may_be_one():
    gate = Gate(PEOPLE)
    req = request(gate, "ana")
    assert gate.decide(req.request_id, dec_proof("ana", req), True, AT).status == "pending"
    assert gate.decide(req.request_id, dec_proof("ben", req), True, AT).status == "approved"
    assert [a["outcome"] for a in gate.audit] == ["requested", "approval", "approval", "approved"]


@pytest.mark.parametrize("who,age,args,code", [
    ("ben", 10, {"cluster": "y"}, "proof_not_for_this"),
    ("ben", 301, None, "stale_proof"),
    ("cy", 10, None, "wrong_role"),
    ("incident-assistant", 10, None, "agents_may_not_approve"),
])
def test_todo3_decision_refusals_are_audited(who, age, args, code):
    gate = Gate(PEOPLE)
    req = request(gate, "ana")
    assert refused(gate.decide, req.request_id, dec_proof(who, req, age, args=args), True, AT) == code
    assert gate.audit[-1]["outcome"] == "refused" and gate.audit[-1]["code"] == code


def test_todo3_a_proof_works_once_and_for_one_request():
    gate = Gate(PEOPLE)
    one, two = request(gate, "ana"), request(gate, "ana", args={"cluster": "z"})
    p = dec_proof("ben", one)
    gate.decide(one.request_id, p, True, AT)
    assert refused(gate.decide, two.request_id, p, True, AT) == "proof_not_for_this"
    three = request(gate, "ana", args={"cluster": "w"})
    p3 = dec_proof("ben", three)
    gate.decide(three.request_id, p3, False, AT)
    assert refused(gate.decide, three.request_id, p3, True, AT) == "not_pending"
    four = request(gate, "ana", args={"cluster": "v"})
    p4 = dec_proof("ben", four)
    gate.decide(four.request_id, p4, True, AT)
    gate.requests[four.request_id].status = "pending"  # even if a request were reopened, the proof is spent
    assert refused(gate.decide, four.request_id, p4, True, AT) == "proof_reused"


def test_todo3_requests_expire_after_15_minutes():
    gate = Gate(PEOPLE)
    req = request(gate, "ana")
    late = AT + timedelta(minutes=16)
    p = make_proof(PEOPLE, "ben", late, purpose="decide", request_id=req.request_id, args_sha256=req.args_sha256)
    assert refused(gate.decide, req.request_id, p, True, late) == "expired" and req.status == "expired"


def test_todo3_the_requester_is_authenticated_and_one_person_actions_need_someone_else():
    gate = Gate(PEOPLE)
    forged = req_proof("incident-assistant", "worker.restart", {"s": 1}, people={**PEOPLE, "key_hex": "22" * 32})
    assert refused(gate.request, "worker.restart", {"s": 1}, forged, AT, because="H1",
                   verdicts=VERDICTS) == "bad_proof"
    req = request(gate, "ana", action="worker.restart", args={"s": 1})
    assert req.requester == "ana"
    assert refused(gate.decide, req.request_id, dec_proof("ana", req), True, AT) == "requester_may_not_approve"
    assert refused(gate.decide, "nothing#9", dec_proof("ben", req), True, AT) == "no_such_request"


def test_todo3_hypotheses_and_kill_switches():
    gate = Gate(PEOPLE)
    # An agent may not act on an unsupported hypothesis; a person may, with a written reason that is audited.
    assert refused(request, gate, "incident-assistant", because="H0") == "unsupported_hypothesis"
    assert refused(request, gate, "ana", because="H0") == "override_reason_required"
    req = request(gate, "ana", because="H0", age_s=11, override="failing over is the owner's call")  # new proof
    assert req.status == "pending" and gate.audit[-2]["outcome"] == "override"
    # Kill switches: any person may trip one at once; the assistant may not; nobody restores here.
    assert request(gate, "ana", action="killswitch.trip", args={"agent": "a"}, because=None).status == "approved"
    assert refused(request, gate, "incident-assistant", action="killswitch.trip", args={"agent": "a"},
                   because=None) == "agents_may_not_trip"
    assert refused(request, gate, "ana", action="killswitch.restore", args={"agent": "a"}) == "not_through_this_gate"


def test_todo3_a_rollback_needs_a_recent_deploy():
    gate = Gate(PEOPLE, deploys=[AT - timedelta(hours=3)])
    code = refused(request, gate, "ana", action="deploy.rollback", args={"d": 1})
    assert code == "precondition_failed:no_deploy_in_2h"


# ---------------------------------------------------------------- TODO 4

GOOD = """# Postmortem

## Summary
x
## Impact
x
## Timeline
- 10:00 thing [ref: alert:A]
## Detection
x
## Diagnosis
Root cause: H2 (supported).
## Contributing factors
- The alert routing missed sign-in events.
## What went well
x
## Action items
| Item | Type | Owner | Due |
| --- | --- | --- | --- |
| Add a rule | detection | ana | 2027-03-08 |
"""


def test_todo4_a_clean_postmortem_has_no_findings():
    assert check(GOOD, ["ana", "ben"]) == []


def test_todo4_each_rule():
    bad = GOOD.replace("## Impact\nx\n", "").replace("[ref: alert:A]", "").replace("(supported)", "")
    bad = bad.replace("The alert routing missed sign-in events.", "ben was careless.")
    bad = bad.replace("| detection | ana | 2027-03-08 |", "| process | | |")
    assert check(bad, ["ana", "ben"]) == [
        ("PM001", "Impact"), ("PM002", "10:00 thing"), ("PM003", "careless"), ("PM004", "Add a rule"),
        ("PM005", "Add a rule: process"), ("PM006", "ben"), ("PM007", "Root cause: H2 .")]

"""TODO 3 (stages), TODO 4 (admission) and TODO 5 (Gate G4's row), on constructed candidates."""

import copy

import pytest

from conftest import RELAY
from pipeline import load_json
from pipeline.admission import admit
from pipeline.signing import log, log_entry_ok, sign, signature_ok
from pipeline.stages import run_pipeline

POLICY = load_json(RELAY / "deploy" / "admission" / "policy.json")
TRUST = {"hmac_key": "k", "log_key": "l"}
OK_GATES = {"test": "success", "eval": "success", "adversarial": "success", "scan": "success"}
GATE_TYPE = POLICY["gate_results"]["type"]
SHA_A = "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"  # sha256 of "a"
D = {"relay": "sha256:" + "1" * 64, "relay-egress-proxy": "sha256:" + "2" * 64}
ID = "https://github.com/relay-example/relay/.github/workflows/release.yml@refs/tags/v9.9.9"
ATT = POLICY["attestations"]


def bundle(digest, identity=ID, attest=ATT, tlog="2027-05-04T14:05:00Z", subject=None, gates=OK_GATES):
    cert = {"issuer": POLICY["issuer"], "identity": identity, "not_before": "2027-05-04T14:00:00Z",
            "not_after": "2027-05-04T14:10:00Z"}
    s = subject or digest
    atts = [{"type": t, "subject": s} for t in attest]
    if gates is not None:
        atts.append({"type": GATE_TYPE, "subject": s, "predicate": dict(gates)})
    b = sign(cert, {"subject": s, "attestations": atts}, "k")
    return log(b, tlog, 7, "l") if tlog else b


def bundles(**over):
    out = {n: bundle(d) for n, d in D.items()}
    out.update(over)
    return out


def desired(**images):
    return {"release": "9.9.9", "images": {**D, **images}}


def rules(d=None, b=None):
    return [(f.rule, f.image) for f in admit(d or desired(), bundles() if b is None else b, POLICY, TRUST)]


# --- the provided stand-in signature ------------------------------------------------------------------------

def test_the_stand_in_signature_detects_any_change():
    b = bundle(D["relay"])
    assert signature_ok(b, "k") and not signature_ok(b, "other")
    b2 = copy.deepcopy(b)
    b2["statement"]["subject"] = D["relay-egress-proxy"]
    assert not signature_ok(b2, "k")
    assert log_entry_ok(b, "l") and not log_entry_ok(b, "other")
    forged = dict(b, tlog=dict(b["tlog"], integrated_time="2027-05-04T14:01:00Z"))
    assert not log_entry_ok(forged, "l")


# --- TODO 4 -------------------------------------------------------------------------------------------------

def test_a_correct_release_is_admitted():
    assert rules() == []


@pytest.mark.parametrize("d, b, expected", [
    (desired(relay="registry.relay.example/relay:9.9.9"), None, [("AD001", "relay")]),
    (desired(relay="sha256:abc"), None, [("AD001", "relay")]),
    (None, bundles(relay=None), [("AD002", "relay")]),
    (None, bundles(relay={**bundle(D["relay"]), "signature": "0" * 64}), [("AD002", "relay")]),
    (None, bundles(relay=bundle(D["relay"], identity=ID.replace("refs/tags/v9.9.9", "refs/heads/agent/x"))),
     [("AD003", "relay")]),
    (None, bundles(relay=bundle(D["relay"], identity=ID.replace("v9.9.9", "v9.9.8"))), [("AD003", "relay")]),
    (None, bundles(relay=bundle(D["relay"], tlog=None)), [("AD004", "relay")]),
    (None, bundles(relay=bundle(D["relay"], tlog="2027-05-04T15:00:00Z")), [("AD004", "relay")]),
    (None, bundles(relay={**bundle(D["relay"]), "tlog": {"integrated_time": "2027-05-04T14:05:00Z"}}),
     [("AD004", "relay")]),
    (None, bundles(relay=bundle(D["relay"], gates=None)), [("AD008", "relay")]),
    (None, bundles(relay=bundle(D["relay"], gates={**OK_GATES, "adversarial": "failure"})), [("AD008", "relay")]),
    (None, bundles(relay=bundle(D["relay"], subject=D["relay-egress-proxy"])), [("AD005", "relay"), ("AD006", "relay"),
                                                                         ("AD008", "relay")]),
    (None, bundles(relay=bundle(D["relay"], attest=ATT[:2])), [("AD006", "relay")]),
    (desired(sidecar="sha256:" + "3" * 64), None, [("AD007", "sidecar")]),
])
def test_each_admission_rule(d, b, expected):
    if b is not None:
        b = {k: v for k, v in b.items() if v is not None}
    assert rules(d, b) == expected


# --- TODO 3 -------------------------------------------------------------------------------------------------

def candidate(**over):
    c = {"id": "X", "version": "9.9.9", "commit": "c", "tests": {"passed": 10, "failed": []},
         "eval": {"policy": "triage-gate-v1", "decision": "PASS", "items": [
             {"item_id": "A", "slices": ["kind:adversarial"], "answer": "a", "judge_verdict": "pass",
              "human_label": "pass", "labeller": "tomas.b", "label_answer_sha256": SHA_A}]},
         "coverage": {"policy": "relay-coverage-gate-v2", "release": "9.9.9", "passed": True, "reasons": []},
         "scans": {n: {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": t}}, "results": []}]}
                   for n, t in (("semgrep", "Semgrep"), ("gitleaks", "gitleaks"), ("trivy", "Trivy"))},
         "bundles": bundles(), "desired": desired(), "running": dict(D)}
    c.update(over)
    return c


def run(c, mode="deliver"):
    r = run_pipeline(c, mode, POLICY, TRUST)
    return r.outcome, [(s.name, s.status) for s in r.stages]


def test_a_clean_candidate_runs_every_stage_and_deploys():
    outcome, stages = run(candidate())
    assert outcome == "deployed"
    assert stages == [("build", "pass"), ("test", "pass"), ("eval", "pass"), ("adversarial", "pass"),
                      ("scan", "pass"), ("release", "pass"), ("admit", "pass"), ("deploy", "pass"), ("verify", "pass")]


def test_every_gate_runs_even_after_one_fails_and_nothing_after_them_in_deliver_mode():
    outcome, stages = run(candidate(tests={"passed": 9, "failed": ["t"]},
                                    coverage={"release": "9.9.9", "passed": False, "reasons": ["C10: 1 of 2"]}))
    assert outcome == "blocked at test"
    assert stages[1:6] == [("test", "fail"), ("eval", "pass"), ("adversarial", "fail"), ("scan", "pass"),
                           ("release", "skipped")]
    assert len(stages) == 6


@pytest.mark.parametrize("over, stage, status", [
    ({"tests": None}, "test", "error"),
    ({"eval": None}, "eval", "error"),
    ({"eval": {"policy": "p", "decision": "FAIL", "failed_rules": ["floor"], "items": []}}, "eval", "fail"),
    ({"eval": {"policy": "p", "decision": "PASS", "items": [{"item_id": "A", "slices": ["kind:adversarial"],
                                                             "answer": "a", "judge_verdict": "pass"}]}}, "eval", "error"),
    ({"eval": {"policy": "p", "decision": "PASS", "items": [{"item_id": "A", "slices": ["kind:adversarial"],
                                                             "answer": "a", "judge_verdict": "pass",
                                                             "human_label": "fail", "labeller": "tomas.b",
                                                             "label_answer_sha256": SHA_A}]}}, "eval", "fail"),
    ({"coverage": {"release": "9.9.8", "passed": True}}, "adversarial", "error"),
    ({"coverage": None}, "adversarial", "error"),
])
def test_gate_failures_and_cannot_decide(over, stage, status):
    _, stages = run(candidate(**over))
    assert (stage, status) in stages


@pytest.mark.parametrize("trivy, status", [
    (None, "error"),
    ({"version": "2.1.0", "runs": []}, "error"),
    ({"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "echo"}}, "results": []}]}, "error"),
    ({"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Trivy"}}, "results": [
        {"ruleId": "R", "properties": {"security-severity": "6.9"}}]}]}, "pass"),
    ({"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Trivy"}}, "results": [
        {"ruleId": "R", "properties": {"security-severity": "7.0"}}]}]}, "fail"),
])
def test_the_scan_stage_fails_closed_on_missing_or_empty_reports(trivy, status):
    c = candidate()
    c["scans"] = dict(c["scans"], trivy=trivy)
    _, stages = run(c)
    assert ("scan", status) in stages


def test_any_gitleaks_result_blocks():
    c = candidate()
    c["scans"]["gitleaks"] = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "gitleaks"}},
                                                             "results": [{"ruleId": "aws-key"}]}]}
    assert run(c)[0] == "blocked at scan"


def test_verify_only_records_everything_and_deploys_nothing():
    outcome, stages = run(candidate(tests={"passed": 9, "failed": ["t"]}, bundles={}), "verify-only")
    assert outcome == "would block at test"
    assert stages[5:] == [("release", "error"), ("admit", "fail"), ("deploy", "skipped")]
    assert run(candidate(), "verify-only")[0] == "would deploy"


def test_an_unset_mode_deploys_nothing():
    outcome, stages = run(candidate(), "")
    assert outcome == "not deployed (mode not set)" and stages[-1] == ("deploy", "skipped")


def test_drift_after_deploy_fails_verify():
    outcome, stages = run(candidate(running={**D, "relay": "sha256:" + "9" * 64}))
    assert outcome == "blocked at verify" and stages[-1] == ("verify", "fail")
    assert run(candidate(running=None))[1][-1] == ("verify", "error")


# --- TODO 5 -------------------------------------------------------------------------------------------------

def test_g4_row_needs_the_gate_and_evidence_for_every_counted_control():
    from pipeline.adversarial import counted, matrix_as_of
    from pipeline.g4 import g4_row
    m = matrix_as_of("4.29.0", "2027-05-04")
    names = counted(m)
    recs = [{"control": n, "date": "2027-04-01", "result": "pass"} for n in names]
    assert g4_row(m, recs, "2027-04-30") == (True, [])
    info = m.controls[names[0]]
    met, reasons = g4_row(m, recs[1:], "2027-04-30")
    assert not met and reasons == [f"{names[0]}: no deployment evidence by 2027-04-30 "
                                   f"(owner {info['deploy_owner']}, due {info['deploy_due']})"]
    assert not g4_row(m, recs[:-1] + [dict(recs[-1], date="2027-05-01")], "2027-04-30")[0]
    assert not g4_row(m, recs[:-1] + [dict(recs[-1], result="fail")], "2027-04-30")[0]
    old = matrix_as_of("4.29.0", "2027-03-22")
    met, reasons = g4_row(old, recs, "2027-04-30")
    assert not met and [r.split(":")[0] for r in reasons] == ["C10", "C11", "C14"]


def test_a_version_that_is_not_x_y_z_is_refused_even_when_signed_at_its_own_tag():
    v = "train-2027-04-01"
    tagged = ID.replace("v9.9.9", "v" + v)
    b = {n: bundle(d, identity=tagged) for n, d in D.items()}
    assert [(f.rule, f.image) for f in admit({"release": v, "images": D}, b, POLICY, TRUST)] == [
        ("AD003", "relay"), ("AD003", "relay-egress-proxy")]


def test_a_revoked_release_is_refused_so_a_rollback_cannot_reach_it():
    pol = dict(POLICY, revoked_releases=["9.9.9"])
    assert [f.rule for f in admit(desired(), bundles(), pol, TRUST)] == ["AD009"]


def test_review_probe_verify_only_images_that_failed_a_gate_are_not_admitted():
    """Round-1 review: a train release signed in verify-only mode after its adversarial gate failed."""
    from pipeline import DATA
    c = load_json(DATA / "train" / "T-2027-04-01.json")
    found = admit(c["desired"], c["bundles"], POLICY, load_json(DATA / "trust-root.json"))
    assert {f.rule for f in found} == {"AD008"} and all("adversarial" in f.message for f in found)
    ok = load_json(DATA / "train" / "T-2027-04-27.json")
    assert admit(ok["desired"], ok["bundles"], POLICY, load_json(DATA / "trust-root.json")) == []

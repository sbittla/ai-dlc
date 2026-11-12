"""Hand-checkable tests for each TODO and each rule. Small inputs; every expected value can be worked out by hand."""

import copy
import hashlib
import json

import pytest

from conftest import DATA_DIR

from capstone import canonical_sha256, coverage, defense, evidence, kinds, redteam, remains, rubric

FIX = DATA_DIR / "fixtures"


# --- TODO 1: tracing sources -------------------------------------------------------------------------------------

def test_trace_sources_reports_missing_unresolved_and_changed(tmp_path):
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    resolve = evidence.resolver({"roots": {}}, tmp_path)
    good = hashlib.sha256(b"one\n").hexdigest()
    assert evidence.trace_sources({"sources": [{"ref": "pack:a.txt", "sha256": good}]}, resolve) == []
    assert evidence.trace_sources({"sources": []}, resolve) == ["no sources: evidence must say what it was produced "
                                                                "from"]
    assert evidence.trace_sources({"sources": [{"ref": "pack:b.txt"}]}, resolve) == \
        ["source 'pack:b.txt' does not resolve"]
    assert evidence.trace_sources({"sources": [{"ref": "pack:a.txt", "sha256": "0" * 64}]}, resolve) == \
        ["source pack:a.txt changed since the item was produced"]


def test_crlf_and_lf_hash_the_same(tmp_path):
    (tmp_path / "w.txt").write_bytes(b"x\r\ny\r\n")
    resolve = evidence.resolver({"roots": {}}, tmp_path)
    lf = hashlib.sha256(b"x\ny\n").hexdigest()
    assert evidence.trace_sources({"sources": [{"ref": "pack:w.txt", "sha256": lf}]}, resolve) == []


def test_references_cannot_climb_out_of_their_root(tmp_path):
    (tmp_path / "inner").mkdir()
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    resolve = evidence.resolver({"roots": {}}, tmp_path / "inner")
    assert resolve("pack:../secret.txt") is None
    assert resolve("pack:/etc/passwd") is None
    assert resolve("nosuchroot:x") is None
    assert resolve("no-colon") is None


# --- TODO 2: coverage by failure domain ---------------------------------------------------------------------------

def _report(depends: dict, cells: dict, harm="exfiltration"):
    return {"policy": {"min_independent_blocking": {"exfiltration": 2, "integrity": 1},
                       "end_to_end_legitimate_case_must_pass": True},
            "controls": {k: {"kind": "blocking", "depends_on": v} for k, v in depends.items()},
            "classes": [{"id": "X1", "harm": harm, "cells": [{"control": c, "status": s, "benign_ok": True}
                                                             for c, s in cells.items()]}]}


def test_two_controls_on_disjoint_domains_count_two():
    r = _report({"a": ["d1"], "b": ["d2"]}, {"a": "verified", "b": "verified"})
    assert coverage.coverage(r["classes"], r["controls"]) == {"X1": 2}
    assert coverage.gate(r) == (True, [])


def test_two_controls_sharing_a_domain_count_once():
    r = _report({"a": ["d1"], "b": ["d1", "d2"]}, {"a": "verified", "b": "verified"})
    assert coverage.coverage(r["classes"], r["controls"]) == {"X1": 1}
    assert coverage.gate(r) == (False, ["X1: 1 of 2 independent verified controls"])


def test_largest_disjoint_set_is_found_not_the_first():
    # a shares with b and with c; b and c are disjoint: the best set is {b, c}
    r = _report({"a": ["d1", "d2"], "b": ["d1"], "c": ["d2"]}, {"a": "verified", "b": "verified", "c": "verified"})
    assert coverage.coverage(r["classes"], r["controls"]) == {"X1": 2}


def test_mitigating_latent_failed_and_absent_cells_never_count():
    r = _report({"a": ["d1"], "b": ["d2"], "c": ["d3"], "e": ["d4"]},
                {"a": "mitigating", "b": "latent", "c": "failed", "e": "absent"}, harm="integrity")
    assert coverage.coverage(r["classes"], r["controls"]) == {"X1": 0}


def test_a_control_that_breaks_the_legitimate_case_fails_the_gate():
    r = _report({"a": ["d1"], "b": ["d2"]}, {"a": "verified", "b": "verified"})
    r["classes"][0]["cells"][1]["benign_ok"] = False
    assert coverage.gate(r) == (False, ["X1: b breaks the legitimate case"])


def test_deployment_gaps_are_counted_controls_without_a_passing_record_by_the_date():
    r = _report({"a": ["d1"], "b": ["d2"]}, {"a": "verified", "b": "verified"})
    r["deployments"] = [{"control": "a", "date": "2027-08-01", "result": "pass"},
                        {"control": "b", "date": "2027-08-20", "result": "pass"}]
    assert coverage.deployment_gaps(r, "2027-08-13") == ["b"]


# --- TODO 3: rubric ceilings ----------------------------------------------------------------------------------------

def test_ceilings_follow_the_state_of_each_required_kind():
    res = evidence.check(FIX / "a-pass")
    assert all(cap == 100 for cap, _ in rubric.ceilings(res).values())
    res = evidence.check(FIX / "a-fail-no-disclosure")
    assert rubric.ceilings(res)["traceability"] == (59, ["disclosure missing"])
    res = evidence.check(FIX / "a-fail-stale")
    assert rubric.ceilings(res)["security"] == (74, ["adversarial has blocking findings"])


def _scores(name="kestrel-a"):
    return json.loads((DATA_DIR / "scores" / f"{name}.json").read_text(encoding="utf-8"))


def test_nobody_can_be_left_off_the_score_sheet():
    res = evidence.check(FIX / "a-pass")
    s = _scores()
    s["members"] = [m for m in s["members"] if m["id"] != "k.cy"]
    with pytest.raises(ValueError, match="RB007"):
        rubric.score(s, res)
    s["members"] = []
    with pytest.raises(ValueError, match="RB007"):
        rubric.score(s, res)
    st = _statements()
    st["members"] = ["k.ade", "k.bo"]
    with pytest.raises(ValueError, match="RB007"):
        rubric.score(_scores(), res, st)


def test_a_blocking_finding_means_g6_is_not_met():
    res = evidence.check(FIX / "a-fail-criterion")
    out = rubric.score(_scores(), res)
    assert all(g == "not met" for _, g in out["g6"])
    assert any(n.startswith("RB009") for n in out["notes"])
    assert all(g == "met" for _, g in rubric.score(_scores(), evidence.check(FIX / "a-pass"))["g6"])


def test_unsound_security_evidence_fails_the_security_gate_whatever_the_panel_says():
    out = rubric.score(_scores(), evidence.check(FIX / "a-fail-overclaim"))
    assert out["gates"]["security"] == "fail" and out["level"] == "Fail"
    assert "RB008 security gate: adversarial blocked" in out["notes"]


def test_an_open_item_is_not_evidence():
    res = evidence.check(FIX / "a-fail-open-label")
    assert res.requirement_state["spec"] == "missing" and res.item_ok["A01"] is False


def test_levels():
    assert [rubric.level(x) for x in (100, 90, 89.9, 75, 74.9, 60, 59.9, 0)] == \
        ["Excellent", "Excellent", "Acceptable", "Acceptable", "Needs work", "Needs work", "Fail", "Fail"]


# --- TODO 4: closing a critical or high finding ------------------------------------------------------------------

def _log():
    return json.loads((DATA_DIR / "redteam" / "osprey-on-kestrel.json").read_text(encoding="utf-8"))


def test_a_clean_log_has_no_findings_and_earns_credit():
    r = redteam.validate(_log())
    assert r["findings"] == [] and r["valid"] == ["RT-01", "RT-02", "RT-03"]
    assert (r["attacker_credit"], r["defender_credit"]) == (3, 2)


def test_high_finding_needs_a_retested_fix_or_a_formal_block_by_an_outsider():
    log = _log()
    f = log["findings"][0]
    f["status"], f["block"] = "blocked", {"owner": "k.ade", "due": "2027-08-20", "reviewer": "k.bo"}
    assert [x.code for x in redteam.validate(log)["findings"]] == ["RT005"]      # reviewer is a defender
    f["block"]["reviewer"] = "security reviewer"
    assert redteam.validate(log)["findings"] == []
    del f["block"]["due"]
    assert [x.code for x in redteam.validate(log)["findings"]] == ["RT005"]


def test_fixed_without_retest_is_rt007_and_still_open():
    log = _log()
    log["findings"][0]["fix"] = {"pr": "#41"}
    assert [x.code for x in redteam.validate(log)["findings"]] == ["RT007", "RT005"]


def test_the_bad_log_breaks_each_rule_once():
    log = json.loads((DATA_DIR / "redteam" / "osprey-on-kestrel-bad.json").read_text(encoding="utf-8"))
    codes = [f.code for f in redteam.validate(log)["findings"]]
    assert codes == ["RT001", "RT006", "RT002", "RT004", "RT007", "RT005"]


def test_the_defending_team_must_be_named_and_match_the_pack():
    log = _log()
    log["defender_members"] = []
    assert [f.code for f in redteam.validate(log)["findings"]][:1] == ["RT010"]
    log = _log()
    f = log["findings"][0]
    f["status"], f["block"] = "blocked", {"owner": "k.ade", "due": "2027-08-20", "reviewer": "k.bo"}
    log["defender_members"] = ["k.ade"]                    # k.bo left off, so k.bo looks independent
    codes = [x.code for x in redteam.validate(log, ["k.ade", "k.bo", "k.cy"], "kestrel")["findings"]]
    assert codes == ["RT010"]
    assert [x.code for x in redteam.validate(log)["findings"]] == []   # outside a pack the kit cannot know
    log["defender"], log["defender_members"] = "kestrel-sla", ["nobody"]   # renamed so the pack check is skipped
    codes = [x.code for x in redteam.validate(log, ["k.ade", "k.bo", "k.cy"], "kestrel")["findings"]]
    assert codes == ["RT010"]


def test_a_high_finding_not_reproduced_closes_only_with_an_outside_confirmation():
    log = _log()
    f = log["findings"][0]
    f["status"] = "not reproduced"
    f.pop("fix")
    assert [x.code for x in redteam.validate(log)["findings"]] == ["RT005"]
    f["confirmed_by"] = "k.bo"
    assert [x.code for x in redteam.validate(log)["findings"]] == ["RT005"]
    f["confirmed_by"] = "security reviewer"
    assert redteam.validate(log)["findings"] == []


def test_attacking_yourself_and_duplicate_ids():
    log = _log()
    log["attacker"] = log["defender"]
    log["findings"].append(copy.deepcopy(log["findings"][2]))
    codes = [f.code for f in redteam.validate(log)["findings"]]
    assert codes == ["RT008", "RT009"]


# --- TODO 5: the defense draw ----------------------------------------------------------------------------------------

def _statements(name="kestrel"):
    return json.loads((DATA_DIR / "defense" / f"{name}-statements.json").read_text(encoding="utf-8"))


PACK_DIR = FIX / "a-pass"


def _pack(name="a-pass"):
    return json.loads((FIX / name / "pack.json").read_text(encoding="utf-8"))


def _pack_copy(tmp_path, edit_prs=None):
    """a-pass copied to tmp_path, its PR record optionally edited and re-hashed (as a team could)."""
    import shutil
    d = tmp_path / "pack"
    shutil.copytree(PACK_DIR, d)
    if edit_prs:
        rec = d / "records" / "prs.json"
        data = json.loads(rec.read_text(encoding="utf-8"))
        edit_prs(data["prs"])
        rec.write_text(json.dumps(data), encoding="utf-8")
        pk = json.loads((d / "pack.json").read_text(encoding="utf-8"))
        pk["prs_record"]["sha256"] = hashlib.sha256(rec.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        (d / "pack.json").write_text(json.dumps(pk), encoding="utf-8")
    return json.loads((d / "pack.json").read_text(encoding="utf-8")), d


def _commit(seed):
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def test_nobody_draws_a_part_they_wrote_and_the_draw_is_reproducible():
    st = _statements()
    for seed in ("s1", "s2", "s3", "kestrel-panel-2027-08-17"):
        draws = defense.draw(st, seed, _commit(seed), _pack(), PACK_DIR)
        assert draws == defense.draw(st, seed, _commit(seed), _pack(), PACK_DIR)
        for d in draws:
            assert d["member"] not in d["authors"] and not d["solo"]


def test_the_draw_is_the_smallest_digest_among_the_candidates():
    st = _statements()
    seed = "s1"
    d = defense.draw(st, seed, _commit(seed), _pack(), PACK_DIR)[0]
    cands = [p["id"] for p in st["parts"] if "k.ade" not in p["authors"]]
    want = min(cands, key=lambda p: hashlib.sha256(f"{seed}|{st['frozen_sha256']}|k.ade|{p}".encode()).hexdigest())
    assert d["part"] == want


def test_statements_changed_after_the_freeze_are_refused():
    st = _statements()
    st["parts"][0]["authors"] = ["k.bo"]
    with pytest.raises(ValueError, match="DF001"):
        defense.draw(st, "s1", _commit("s1"), _pack(), PACK_DIR)


def test_a_seed_that_does_not_match_the_commitment_is_refused():
    with pytest.raises(ValueError, match="DF004"):
        defense.draw(_statements(), "s1", _commit("s2"), _pack(), PACK_DIR)


def test_a_solo_learner_draws_from_every_part():
    st = _statements("lark")
    d = defense.draw(st, "s1", _commit("s1"))
    assert d[0]["solo"] is True and d[0]["part"] in {"P01", "P02"}


def test_unknown_authors_are_df003():
    st = _statements()
    st["parts"][0]["authors"] = ["k.zed"]
    st["frozen_sha256"] = canonical_sha256({"members": st["members"], "parts": st["parts"]})
    assert [f.code for f in defense.check(st, _pack(), PACK_DIR)] == ["DF003", "DF005"]


def test_overclaimed_coauthorship_cannot_aim_the_draw():
    # k.cy claims to have co-written every part but P02, which would force P02 under any seed
    st = _statements()
    for p in st["parts"]:
        if p["id"] != "P02" and "k.cy" not in p["authors"]:
            p["authors"].append("k.cy")
    st["frozen_sha256"] = canonical_sha256({"members": st["members"], "parts": st["parts"]})
    codes = [f.code for f in defense.check(st, _pack(), PACK_DIR)]
    assert "DF005" in codes and "DF006" in codes          # not the pack's PR authors; pool of 1 < 4



def test_an_inflated_pr_record_is_still_bounded_by_the_pool(tmp_path):
    st = _statements()
    for p in st["parts"]:
        if p["id"] != "P02" and "k.cy" not in p["authors"]:
            p["authors"].append("k.cy")
    st["frozen_sha256"] = canonical_sha256({"members": st["members"], "parts": st["parts"]})

    def inflate(prs):
        for pr in prs:
            if pr["id"] != "#14":
                pr["authors"] = sorted(set(pr["authors"]) | {"k.cy"})
    pack, d = _pack_copy(tmp_path, inflate)
    assert [f.code for f in defense.check(st, pack, d)] == ["DF006"]
    with pytest.raises(ValueError, match="DF006"):
        defense.draw(st, "s1", _commit("s1"), pack, d)


def test_every_recorded_pr_must_belong_to_a_part():
    st = _statements()
    st["parts"] = [p for p in st["parts"] if p["id"] != "P07"]          # #23 could then never be drawn
    st["frozen_sha256"] = canonical_sha256({"members": st["members"], "parts": st["parts"]})
    assert ("DF008", "#23") in [(f.code, f.where) for f in defense.check(st, _pack(), PACK_DIR)]


def test_an_edited_pr_record_is_refused(tmp_path):
    pack, d = _pack_copy(tmp_path)
    (d / "records" / "prs.json").write_text('{"prs": []}', encoding="utf-8")   # hash not updated
    assert ("DF008", "prs_record") in [(f.code, f.where) for f in defense.check(_statements(), pack, d)]
    assert any(f.code == "EV010" and f.where == "prs_record" for f in evidence.check(d).findings)


def test_the_part_list_needs_an_instructors_approval():
    st = _statements()
    st.pop("parts_approved")
    assert [f.code for f in defense.check(st, _pack(), PACK_DIR)] == ["DF009"]
    st["parts_approved"] = {"by": "k.bo", "date": "2027-08-06"}          # a member cannot be the approver
    assert [f.code for f in defense.check(st, _pack(), PACK_DIR)] == ["DF009"]


def test_red_team_evidence_must_be_an_attack_on_the_teams_own_system(tmp_path):
    import shutil
    d = tmp_path / "pack"
    shutil.copytree(PACK_DIR, d)
    log_path = d / "items" / "redteam-log.json"
    log = json.loads(log_path.read_text(encoding="utf-8"))
    log["attacker"], log["defender"] = "kestrel", "osprey"              # kestrel attacked osprey instead
    log["defender_members"] = ["o.ade", "o.bo", "o.cy"]
    log_path.write_text(json.dumps(log), encoding="utf-8")
    pk = json.loads((d / "pack.json").read_text(encoding="utf-8"))
    for it in pk["items"]:
        if it["id"] == "A06":
            it["sha256"] = hashlib.sha256(log_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    (d / "pack.json").write_text(json.dumps(pk), encoding="utf-8")
    res = evidence.check(d)
    assert [(f.code, f.where) for f in res.blocking] == [("EV004", "A06")]
    out = rubric.score(_scores(), res)
    assert out["gates"]["security"] == "fail" and "RB008 security gate: red-team blocked" in out["notes"]


def test_a_team_draw_needs_its_pack():
    with pytest.raises(ValueError, match="DF007"):
        defense.draw(_statements(), "s1", _commit("s1"))


# --- the checker as a whole: every fixture fails in its stated way ----------------------------------------------

EXPECTED = {
    "a-pass": set(), "b-pass": set(), "c-pass": set(), "d-pass": set(),
    "a-fail-no-disclosure": {"EV001"}, "a-fail-tampered": {"EV003"}, "a-fail-untraced": {"EV005"},
    "a-fail-stale": {"EV008"}, "a-fail-overclaim": {"EV004", "EV011"}, "a-fail-criterion": {"EV006"},
    "a-fail-label": {"EV007"}, "a-fail-open-high": {"EV011"}, "a-fail-interval": {"EV004"},
    "a-fail-owner": {"EV010"}, "a-fail-no-release": {"EV008"}, "a-fail-file-release": {"EV008"},
    "a-fail-open-label": {"EV001"}, "a-fail-thin-disclosure": {"EV004"}, "a-fail-redteam-members": {"EV004"}, "b-fail-merge-tool": {"EV011"}, "b-fail-case-evidence": {"EV004"},
    "c-fail-roi": {"EV011"}, "c-fail-operating-model": {"EV011"}, "c-fail-pilot-wording": {"EV004"},
    "c-fail-maturity-claim": {"EV004"}, "d-fail-attack-text": {"EV012"}, "d-fail-shared-domain": {"EV011"},
    "d-fail-self-review": {"EV004", "EV006"}, "d-fail-drill": {"EV011", "EV006"}, "d-fail-asr-scope": {"EV004"},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_fixture_fails_only_in_its_stated_way(name):
    res = evidence.check(FIX / name)
    assert {f.code for f in res.blocking} == EXPECTED[name]


def test_every_fixture_is_listed():
    assert {p.name for p in FIX.iterdir() if (p / "pack.json").exists()} == set(EXPECTED)


def test_simulated_results_cannot_be_labelled_verified(tmp_path):
    item = {"label": "verified"}
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"dataset": "d", "version": "1", "metric": "m", "n": 10, "successes": 9, "runs": 3,
                             "interval": [round(x, 4) for x in kinds.wilson(9, 10)], "threshold": 0.8,
                             "simulated": True}), encoding="utf-8")
    bad, failing, _ = kinds.v_eval_record(p, item, {})
    assert bad == ["simulated results labelled verified"] and failing == []


def test_wilson_matches_chapter_2():
    lo, hi = kinds.wilson(68, 90)
    assert (round(lo, 3), round(hi, 3)) == (0.658, 0.833)


def test_remains_never_invents_a_date():
    rows = remains.view("2027-07-26")["rows"]
    for r in rows:
        assert r["status"] == ("no date recorded" if not r["due"] else
                               "date passed, no completion recorded" if r["due"] < "2027-07-26" else "due later")


@pytest.mark.parametrize("tid, ok", [("T1", True), ("T15", True), ("T16", True), ("T17", True),
                                     ("T0", False), ("T18", False), ("T01", False)])
def test_track_d_accepts_owasp_agentic_t1_to_t17_only(tmp_path, tid, ok):
    p = tmp_path / "tm.json"
    p.write_text(json.dumps({"system": "s", "components": ["c"], "boundaries": [{"id": "B1"}],
                             "threats": [{"id": "X1", "boundary": "B1", "owasp_llm": "LLM01", "owasp_agentic": tid,
                                          "atlas": "AML.T0051", "controls": ["egress"]}]}), encoding="utf-8")
    bad, failing, _ = kinds.v_threat_model(p, {}, {"track": "D"})
    assert bad == ([] if ok else ["X1: no OWASP Agentic threat ID"]) and failing == []

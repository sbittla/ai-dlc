"""Governing autonomy (4.31.0, ADR-056): the metrics and their intervals, the T4 criteria failing closed, the
guard metric and its rollback rule, the safety case checker, and the DST table task's own checks (ADR-010)."""

import json

import pytest

from maintenance_helpers import POLICY, ROOT
from relay.escalation import hours
from relay.maintenance import eligibility, judge, mcnemar_exact, metrics, runs_needed, verdict, wilson
from relay.maintenance import safety_case, tables
from relay.maintenance.guard import Window


def test_wilson_and_the_number_of_clean_runs_a_5_percent_bound_needs():
    lo, hi = wilson(0, 12)
    assert lo == 0.0 and round(hi, 3) == 0.242
    assert runs_needed(0.05) == 73 and wilson(0, 73)[1] <= 0.05 < wilson(0, 72)[1]
    assert round(mcnemar_exact(3, 0), 3) == 0.25 and mcnemar_exact(0, 0) == 1.0
    assert round(mcnemar_exact(9, 1), 4) == 0.0215


LOG = [{"task_type": "docs-upkeep", "outcome": "merged", "usd": 0.04} for _ in range(10)] + [
    {"task_type": "docs-upkeep", "outcome": "merged", "usd": 0.05, "intervention": True},
    {"task_type": "docs-upkeep", "outcome": "denied", "usd": 0.03, "violations": 1, "intervention": True},
    {"task_type": "dependency-update", "outcome": "merged", "usd": 0.0, "rolled_back": True}]
DRILL = {"on": "2027-06-30", "status": "deployed", "record": "drill log"}
EVIDENCE = {"coverage_gate": "pass", "live_attack_measurement": None, "killswitch_drill": DRILL,
            "rollback_drill": {**DRILL, "on": "2027-06-29"}, "scan_catch_rate": [83, 100]}


def test_metrics_count_success_harm_interventions_violations_and_cost():
    m = metrics(LOG, "docs-upkeep")
    assert (m.runs, m.merged, m.success.k, m.harm.k, m.intervention.k, m.violations) == (12, 11, 11, 0, 2, 1)
    assert round(m.usd, 2) == 0.48 and round(m.usd_per_success, 4) == 0.0436
    d = metrics(LOG, "dependency-update")
    assert (d.rollback.k, d.harm.k, d.success.k) == (1, 1, 0) and d.usd_per_success is None


def test_the_criteria_fail_closed_on_small_samples_violations_and_missing_measurements():
    c = {x.cid: x for x in eligibility(metrics(LOG, "docs-upkeep"), True, EVIDENCE, "2027-07-09")}
    assert not c["A1"].passed and "73 merged changes" in c["A1"].detail
    assert not c["A2"].passed and not c["A3"].passed
    assert not c["A4"].passed and "live attack measurement missing" in c["A4"].detail
    assert c["A5"].passed and c["A6"].passed and c["A7"].passed
    assert verdict(list(c.values())) == "not eligible (A1, A2, A3, A4)"
    old = {**EVIDENCE, "killswitch_drill": {**DRILL, "on": "2027-01-05"}}
    stale = eligibility(metrics(LOG, "docs-upkeep"), False, old, "2027-07-09")
    assert [x.cid for x in stale if not x.passed] == ["A1", "A2", "A3", "A5"]


def test_a_drill_counts_only_if_deployed_and_dated_in_the_last_90_days():
    m = metrics(LOG, "docs-upkeep")
    for bad in ("2027-06-30", {**DRILL, "status": "modelled"}, {**DRILL, "status": "verified"},
                {**DRILL, "on": "2027-07-10"}, None):
        c = {x.cid: x for x in eligibility(m, False, {**EVIDENCE, "killswitch_drill": bad}, "2027-07-09")}
        assert not c["A5"].passed, bad
    assert {x.cid: x for x in eligibility(m, False, EVIDENCE, "2027-07-09")}["A5"].passed


def test_enough_clean_runs_and_every_prerequisite_make_a_candidate_not_a_grant():
    log = [{"task_type": "docs-upkeep", "outcome": "merged", "usd": 0.04} for _ in range(80)]
    evidence = {**EVIDENCE, "live_attack_measurement": {"owner": "aisha.r", "rate": "recorded"}}
    assert verdict(eligibility(metrics(log, "docs-upkeep"), True, evidence, "2027-07-09")) == "candidate for a grant"
    assert POLICY.task("docs-upkeep").tier == "T2"   # the grant itself is a policy change two people approve


def test_the_guard_trips_on_a_sign_in_failure_jump_and_not_on_noise_or_thin_windows():
    windows = [Window(1, 10, 1, 190, 5), Window(2, 40, 2, 760, 30), Window(3, 30, 12, 780, 25)]
    d = judge(windows)
    assert d.minute == 3 and round(d.canary_share, 3) == 0.286 and d.z > 2.326
    assert judge([Window(1, 40, 3, 760, 30), Window(2, 41, 2, 770, 31)]).minute is None


CASE = {"case": "t", "status": "draft", "claims": [
    {"id": "C0", "text": "top"},
    {"id": "C1", "parent": "C0", "text": "cannot change itself", "evidence": ["E1"]},
    {"id": "C2", "parent": "C0", "text": "stops on budget", "evidence": ["E2", "E3"]}],
    "evidence": [{"id": "E1", "ref": "test:protected", "required_status": "verified"},
                 {"id": "E2", "ref": "test:budget", "required_status": "verified"},
                 {"id": "E3", "ref": "drill:killswitch", "required_status": "deployed"}],
    "defeaters": [{"id": "D1", "against": "C1", "text": "same-process checks", "status": "open"}]}
RESULTS = {"test:protected": {"status": "verified", "result": "pass"},
           "test:budget": {"status": "verified", "result": "pass"},
           "drill:killswitch": {"status": "modelled", "result": "pass"}}


def test_the_case_checker_names_weak_evidence_and_open_defeaters():
    people, teams = set(POLICY.teams["@relay/maintainers"]) | {"aisha.r", "lena.k"}, dict(POLICY.teams)
    problems = safety_case.check(CASE, RESULTS, people, teams, "priya.n")
    assert problems == ["too_weak:E3", "open_defeater:D1"]
    assert safety_case.supported(CASE, RESULTS) == {"C0": False, "C1": False, "C2": False}
    tested_only = {**RESULTS, "drill:killswitch": {"status": "verified", "result": "pass"}}
    assert "too_weak:E3" in safety_case.check(CASE, tested_only, people, teams, "priya.n")  # a test is not a drill
    approved = {**CASE, "status": "approved", "approvals": [{"by": "priya.n"}, {"by": "sam.o"}]}
    assert "approval:the bot's owner may not approve" in safety_case.check(approved, RESULTS, people, teams,
                                                                            "priya.n")


def test_the_dst_rules_reproduce_the_reviewed_years_before_extending_the_table():
    rules = json.loads((ROOT / "maintenance" / "dst-rules.json").read_text(encoding="utf-8"))
    table = {n: getattr(hours, n) for n in tables.NAMES}
    assert tables.check_rules(rules, table, [2026, 2027], hours.COVERED_FROM, hours.COVERED_UNTIL) == (20, 20)
    new = tables.extend((ROOT / "src" / "relay" / "escalation" / "hours.py").read_text(encoding="utf-8"), rules, 2028)
    assert "COVERED_UNTIL = datetime(2029, 1, 1, tzinfo=UTC)" in new and "_z(2028, 3, 26, 1)" in new
    assert "(_z(2027, 10, 2, 16), _z(2028, 4, 1, 16)), (_z(2028, 9, 30, 16), COVERED_UNTIL)" in new
    broken = json.loads(json.dumps(rules))
    broken["zones"]["_EU"]["start"]["week"] = "first"
    assert tables.check_rules(broken, table, [2026, 2027], hours.COVERED_FROM, hours.COVERED_UNTIL)[0] < 20


def test_the_tests_that_pin_the_tables_old_end_are_listed_for_a_person():
    files = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted((ROOT / "tests" / "escalation").glob("*.py"))}
    assert tables.pinned_tests(files, 2027) == ["tests/escalation/test_escalation_engine.py",
                                                "tests/escalation/test_escalation_hours.py",
                                                "tests/escalation/test_escalation_zones.py"]
    assert all(POLICY.protected(p) or not POLICY.writable("table-extension", p) for p in files)


@pytest.mark.parametrize("bad", ["", "  "])
def test_extend_refuses_text_it_does_not_recognise(bad):
    with pytest.raises(ValueError):
        tables.extend(bad, {"zones": {}}, 2028)

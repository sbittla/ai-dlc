"""Every number Chapter 15 quotes from Lab 15.1. A change to data or code that moves one must fail here."""

from collections import Counter

import pytest

from pipeline.adversarial import counted, coverage, gate, matrix_as_of
from pipeline.report import (g4_numbers, guard_pr, all_prs, incident_numbers, lint_rows, report_timeline,
                             runs, train_numbers)


def test_lint():
    got = {rel: Counter(f.rule for f in fs) for rel, fs in lint_rows()}
    assert all(not got[k] for k in got if k.startswith(".github/"))
    assert len([k for k in got if k.startswith(".github/")]) == 6
    assert sum(got["data/drafts/agent-draft-v1.yml"].values()) == 12
    assert got["data/drafts/agent-draft-v1.yml"] == Counter({"PL005": 3, "PL001": 2, "PL002": 1, "PL004": 1,
                                                             "PL006": 1, "PL007": 1, "PL008": 1, "PL009": 1,
                                                             "PL010": 1})
    assert not got["data/drafts/agent-draft-v2.yml"]


def test_guard():
    got = {pr["number"]: (guard_pr(pr)[1][0], [f.rule for f in guard_pr(pr)[0]]) for pr in all_prs()}
    assert got == {2604: ("block", ["GD004", "GD005", "PG001", "PG002", "PG003"]), 2702: ("pass", []),
                   2715: ("block", ["GD006", "PG003"]), 2720: ("cannot decide", ["PG004"])}


def test_incident():
    n = incident_numbers()
    assert (n["merged_prs"], n["empty_reports"], len(n["would_block"])) == (41, 28, 2)
    assert n["blind"] == 9 * 86400 + 5 * 3600 + 7 * 60
    assert n["to_notice"] == 9 * 86400 + 3 * 3600 + 22 * 60
    assert (n["merged"], n["approved"], n["agent_commit"]) == ("2027-03-01T10:58:00Z", "2027-03-01T10:52:00Z",
                                                               "2027-03-01T09:44:00Z")
    assert n["guard"] == "block" and n["lint_after"] == []


def test_candidates():
    got = {c["id"]: r.outcome for c, r in runs("candidates", "deliver")}
    assert got == {"P-01": "deployed", "P-02": "blocked at test", "P-03": "blocked at eval",
                   "P-04": "blocked at eval (cannot decide)", "P-05": "blocked at eval",
                   "P-06": "blocked at adversarial", "P-07": "blocked at scan", "P-08": "blocked at scan (cannot decide)",
                   "P-09": "blocked at release (cannot decide)", "P-10": "blocked at admit", "P-11": "blocked at admit",
                   "P-12": "blocked at verify"}
    vo = {c["id"]: r.outcome for c, r in runs("candidates", "verify-only")}
    assert vo["P-01"] == "would deploy" and vo["P-09"] == "would block at release"


def test_verify_only_beside_the_train():
    n = train_numbers()
    assert (n["releases"], n["shipped"], len(n["would_deploy"])) == (31, 31, 4)
    assert n["would_deploy"] == ["T-2027-04-27", "T-2027-04-28", "T-2027-04-29", "T-2027-04-30"]
    assert n["first"] == {"eval": 6, "adversarial": 21}
    assert n["any"] == {"eval": 6, "adversarial": 27, "scan": 1, "release": 1, "admit": 27}


def test_coverage_on_the_final_code():
    m = matrix_as_of("4.29.0", "2027-04-30")
    assert Counter(c.status for c in m.cells) == Counter({"verified": 30, "mitigating": 17, "latent": 9})
    assert len(m.cells) == 56 and len(counted(m)) == 10
    assert gate(m) == (True, [])
    cov = coverage(m)
    assert (cov["C10"], cov["C11"], cov["C14"]) == (2, 2, 1)
    old = matrix_as_of("4.29.0", "2027-03-22")
    assert Counter(c.status for c in old.cells)["verified"] == 27 and len(counted(old)) == 8


@pytest.mark.parametrize("as_of, met, gate_short, missing", [
    ("2027-03-22", False, ["C10", "C11", "C14"], 5),
    ("2027-03-31", False, ["C10", "C11"], 2),
    ("2027-04-27", False, [], 1),
    ("2027-04-30", True, [], 0),
])
def test_g4_timeline(as_of, met, gate_short, missing):
    got_met, reasons = g4_numbers(as_of)
    assert got_met is met
    assert [r.split(":")[0] for r in reasons if "independent verified" in r] == gate_short
    assert sum("no deployment evidence" in r for r in reasons) == missing
    assert "| 2027-04-30 | PASS | 0 of 10 | MET |" in report_timeline()


def test_dates_the_chapter_quotes():
    from pipeline import DATA, load_json
    dates = {r["control"]: r["date"] for r in load_json(DATA / "deployments.json")["records"]}
    assert dates == {"tool_allowlist": "2027-02-25", "approval": "2027-02-25", "platform_permissions": "2027-02-25",
                     "render": "2027-03-29", "human_label": "2027-03-30", "output_constraint": "2027-03-31",
                     "delivery_binding": "2027-03-31", "egress": "2027-04-27", "test_sandbox": "2027-04-27",
                     "memory_review": "2027-04-30"}
    rows = {c["id"]: (c, r) for c, r in train_numbers()["rows"]}
    hot, run = rows["T-2027-04-14-hotfix"]
    assert hot["train"]["time"] == "2027-04-14T18:40:00Z" and run.status("admit") == "fail"
    assert rows["T-2027-04-13"][1].status("scan") == "fail"
    assert [c for c, (_, r) in rows.items() if r.status("eval") == "error"] == [
        "T-2027-03-22", "T-2027-03-23", "T-2027-03-24", "T-2027-03-25", "T-2027-03-26", "T-2027-03-29"]
    events = load_json(DATA / "incident" / "timeline.json")["events"]
    assert [e["at"] for e in events][0] == "2027-03-01T09:12:00Z" and events[-1]["at"] == "2027-03-12T11:30:00Z"

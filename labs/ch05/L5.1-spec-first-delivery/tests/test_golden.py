"""Golden tests: every number Chapter 5 quotes from Lab 5.1. A change that moves one must fail here."""

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter

import pytest
from conftest import DATA_DIR, LAB_ROOT, RELAY_REPO, SPEC_DIR_NAME, TARGET

from speccheck import incident, plan, report
from speccheck.checks import run_checks
from speccheck.core import BLOCKING, CHECKS, WARNING
from speccheck.repo import find_tests
from speccheck.spec import load_prd

PRD = load_prd(DATA_DIR / "prd-v1.md")
TESTS = find_tests(RELAY_REPO / "tests")
V1 = DATA_DIR / "spec-v1"
SCAFFOLD = DATA_DIR / "spec-scaffold"
DRAFT = DATA_DIR / "tasks-draft.md"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def args(*extra):
    return ["--prd", str(DATA_DIR / "prd-v1.md"), "--tests", str(RELAY_REPO / "tests"), *extra]


@pytest.fixture(scope="module")
def v1():
    return run_checks(V1, PRD, TESTS)


@pytest.fixture(scope="module")
def draft():
    return run_checks(V1, PRD, TESTS, DRAFT)


@pytest.fixture(scope="module")
def scaffold():
    return run_checks(SCAFFOLD, PRD, TESTS)


def test_prd_is_lab_4_1s_approved_version():
    digest = hashlib.sha256((DATA_DIR / "prd-v1.md").read_bytes()).hexdigest()
    assert digest == "957a41fd79ebec33e28a40b43b7473df4534deac81071e190cfb88bbad5e9dc1"
    assert (PRD.version, len(PRD.requirements), len(PRD.criteria)) == ("1.0", 21, 31)


def test_reference_spec_has_no_findings_and_its_scope(v1):
    assert v1.findings == ()
    spec = v1.spec
    assert [c.id for c in spec.criteria] == ["ESC-AC02", "ESC-AC06", "ESC-AC08", "ESC-AC09", "ESC-AC10", "ESC-AC11",
                                             "ESC-AC13", "ESC-AC14", "ESC-AC18", "ESC-AC24", "ESC-AC26", "ESC-AC27"]
    assert len({c.requirement for c in spec.criteria}) == 10
    assert [c.id for c in spec.criteria if c.coverage == "partial"] == ["ESC-AC08", "ESC-AC18", "ESC-AC24",
                                                                         "ESC-AC27"]
    assert [c.id for c in spec.constraints] == ["SEC-01", "SEC-02", "SEC-03", "SEC-04", "SEC-05"]
    assert len(v1.contract.fields) == 20 and len(spec.data_rules) == 24
    assert Counter(spec.data_rules.values()) == {"Internal": 19, "Confidential": 5}
    assert (len(spec.codes), len(spec.statuses)) == (10, 4)


def test_scaffold_findings(scaffold):
    assert len(scaffold.findings) == 29
    assert sum(f.blocking for f in scaffold.findings) == 26
    assert Counter(f.code for f in scaffold.findings) == {"SP001": 2, "SP011": 3, "SP023": 12, "SP042": 9,
                                                          "SP060": 1, "SP080": 2}


def test_draft_task_list_findings(draft):
    found = draft.findings
    assert len(found) == 11 and sum(f.blocking for f in found) == 9
    assert Counter(f.severity for f in found) == {"critical": 1, "high": 8, "medium": 2}
    assert {(f.code, f.item) for f in found} == {
        ("SP082", "tasks"), ("SP044", "T02"), ("SP044", "T04"), ("SP043", "T07"), ("SP041", "T03"),
        ("SP040", "T06"), ("SP042", "ESC-AC24"), ("SP042", "SEC-05"), ("SP052", "T04"), ("SP051", "T05"),
        ("SP050", "T07")}


def test_task_graph(v1):
    assert plan.waves(v1.tasks) == [["T01"], ["T02", "T03", "T06"], ["T04", "T07", "T09"], ["T05", "T08"]]
    assert plan.tier_counts(v1.tasks) == {"T2": 9}
    assert [t.id for t in v1.tasks.tasks if t.untrusted == "yes"] == ["T08"]
    assert [t.id for t in v1.tasks.tasks if t.risk == "high"] == ["T04", "T05", "T08", "T09"]


def test_trace_matrix(v1):
    rows = plan.trace_rows(v1.spec, v1.tasks, v1.tests)
    assert rows[2] == ("ESC-R04", "ESC-AC08", "T06", "2")
    assert rows[8] == ("ESC-N01", "ESC-AC18", "T08", "1")
    assert rows[11] == ("ESC-N07", "ESC-AC27", "T01, T02, T09", "1")
    assert sum(int(r[3]) for r in rows) == 15


def test_report_prints_the_chapter_tables(capsys):
    assert report.main(args("--spec", str(SCAFFOLD), "--spec", str(V1), "--spec", str(V1),
                            "--tasks", "-", "--tasks", "-", "--tasks", str(DRAFT))) == 0
    text = capsys.readouterr().out
    for row in ("| PRD criteria in this slice (of 31) | 12 | 12 | 12 |",
                "| PRD requirements in this slice (of 21) | 10 | 10 | 10 |",
                "| Criteria covered fully / partly | 0 / 0 | 8 / 4 | 8 / 4 |",
                "| Security constraints | 1 | 5 | 5 |",
                "| Contract fields classified | 0 of 20 | 20 of 20 | 20 of 20 |",
                "| Tasks | 3 | 9 | 7 |",
                "| Criteria with a test of the same ID | 12 of 12 | 12 of 12 | 12 of 12 |",
                "| **Total open findings** | **29** | **0** | **11** |",
                "| Blocking findings (`--gate`) | 26 | 0 | 9 |",
                "| Warnings | 3 | 0 | 2 |"):
        assert row in text, row


def test_gate_exit_codes():
    assert report.main(args("--spec", str(V1), "--gate")) == 0
    assert report.main(args("--spec", str(SCAFFOLD), "--gate")) == 1
    assert report.main(args("--spec", str(V1), "--tasks", str(DRAFT), "--gate")) == 1


def test_check_catalogue():
    assert len(CHECKS) == 29 and WARNING == {"SP011", "SP031", "SP044"}
    assert BLOCKING | WARNING == set(CHECKS) and len(BLOCKING) == 26
    assert Counter(sev for sev, _, _ in CHECKS.values()) == {"critical": 2, "high": 24, "medium": 3}


def test_incident_three_designs():
    schema = json.loads((V1 / "contracts" / "escalation-rules.schema.json").read_text(encoding="utf-8"))
    result = incident.compare(incident.load(DATA_DIR / "incident"), schema)
    assert result["distinct"] == 27 and result["in_all_three"] == []
    assert result["shared"] == {"A+B": [], "A+C": [], "B+C": ["task_id"]}
    assert [(r["agent"], len(r["rule_errors"]), len(r["evaluation_errors"])) for r in result["rows"]] == [
        ("A", 5, 9), ("B", 11, 9), ("C", 8, 8)]
    assert sum(not r["rule_errors"] and not r["evaluation_errors"] for r in result["rows"]) == 0


def _same_tree(a, b):
    def files(root):
        return {p.relative_to(root).as_posix(): p.read_bytes().replace(b"\r\n", b"\n")
                for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    return files(a) == files(b)


def test_relay_repos_carry_the_data_spec_packages():
    assert _same_tree(LAB_ROOT / "solution" / "relay-repo" / "specs" / SPEC_DIR_NAME, V1)
    assert _same_tree(LAB_ROOT / "starter" / "relay-repo" / "specs" / SPEC_DIR_NAME, SCAFFOLD)


@pytest.mark.skipif(TARGET != "solution", reason="reference counts; your own test count may differ")
def test_reference_suite_counts():
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY_REPO,
                          env=ENV, capture_output=True, text=True, timeout=180)
    assert proc.stdout.strip().splitlines()[-1].startswith("64 passed")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/escalation"],
                          cwd=RELAY_REPO, env=ENV, capture_output=True, text=True, timeout=180)
    assert proc.stdout.strip().splitlines()[-1].startswith("35 passed")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--collect-only",
                           "tests/escalation"], cwd=RELAY_REPO, env=ENV, capture_output=True, text=True, timeout=180)
    modules = Counter(line.split("::")[0].split("/")[-1] for line in proc.stdout.splitlines() if "::" in line)
    assert modules == {"test_escalation_acceptance.py": 19, "test_escalation_contract.py": 13,
                       "test_escalation_policy.py": 3}


def test_generator_reproduces_data_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["incident/agent-a.json", "incident/agent-b.json", "incident/agent-c.json",
                       "spec-scaffold/contracts/escalation-rules.schema.json", "spec-scaffold/spec.md",
                       "spec-scaffold/tasks.md", "tasks-draft.md"]
    for name in written:
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name

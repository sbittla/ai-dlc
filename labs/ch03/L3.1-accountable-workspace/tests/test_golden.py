"""Golden tests: every audit number Chapter 3 quotes. A change that moves one must fail here."""

import sys
from collections import Counter
from datetime import date

import pytest
from conftest import DATA_DIR, RELAY_REPO

from audit import report
from audit.checks import run_audit
from audit.core import load_policy

POLICY = load_policy(DATA_DIR / "policy.json")
AS_OF = date(2026, 11, 8)
BEFORE = DATA_DIR / "repos" / "before"
AFTER = DATA_DIR / "repos" / "after"


@pytest.fixture(scope="module")
def before():
    return run_audit(BEFORE, POLICY, AS_OF)


def test_before_findings_by_severity(before):
    assert Counter(f.severity for f in before.open) == {"critical": 7, "high": 9, "medium": 7, "low": 2}
    assert len(before.open) == 25 and before.waived == ()


def test_before_findings_by_area(before):
    assert Counter(f.area for f in before.open) == {"instructions": 4, "secrets": 6, "sandbox": 4,
                                                    "branch": 9, "mcp": 2}


def test_before_criticals_are_five_secrets_and_two_credential_mounts(before):
    crit = [(f.check, f.path) for f in before.open if f.severity == "critical"]
    assert Counter(c for c, _ in crit) == {"WS010": 5, "WS021": 2}
    assert ("WS010", "AGENTS.md") in crit and ("WS010", ".mcp.json") in crit
    assert sum(p == ".env" for _, p in crit) == 3


def test_after_has_nothing_open_and_one_waiver():
    after = run_audit(AFTER, POLICY, AS_OF)
    assert after.open == ()
    assert [(f.check, f.severity) for f in after.waived] == [("WS023", "low")]


def test_waiver_expiry_reopens_the_finding():
    after = run_audit(AFTER, POLICY, date(2027, 2, 1))
    assert [(f.check, f.severity) for f in after.open] == [("WS023", "low")] and after.waived == ()


def test_the_relay_repo_you_ship_passes_the_audit():
    result = run_audit(RELAY_REPO, POLICY, AS_OF)
    assert result.open == () and [f.check for f in result.waived] == ["WS023"]


def test_report_prints_the_chapter_table():
    text, _ = report.render([BEFORE, AFTER], POLICY, AS_OF)
    for row in ("| critical | 7 | 0 |", "| high | 9 | 0 |", "| medium | 7 | 0 |", "| low | 2 | 0 |",
                "| **Total open** | **25** | **0** |", "| Waived (with owner and expiry) | 0 | 1 |",
                "· 20 checks", "166 lines; policy maximum is 150"):
        assert row in text


@pytest.mark.parametrize("repo,code", [(BEFORE, 1), (AFTER, 0)])
def test_fail_on_high_works_as_a_ci_gate(monkeypatch, capsys, repo, code):
    argv = ["audit.report", "--policy", str(DATA_DIR / "policy.json"), "--as-of", "2026-11-08",
            "--fail-on", "high", str(repo)]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        report.main()
        status = 0
    except SystemExit as exc:
        status = exc.code
    assert status == code

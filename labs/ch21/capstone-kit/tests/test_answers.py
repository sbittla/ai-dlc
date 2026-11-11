"""The arithmetic in book/answers/ch21-answers.md, checked with the kit's own code."""

import copy

from capstone import coverage, redteam
from capstone.evidence import tracks


def test_exercise_5_rubric_arithmetic():
    weights = {d["id"]: d["weight"] for d in tracks()["tracks"]["B"]["dimensions"]}
    raw = {"correctness": 80, "security": 90, "verification": 85, "operations": 70, "reliability": 88,
           "traceability": 92}
    caps = {"security": 59, "traceability": 74}       # red-team log missing; safety case blocked
    counted = {k: min(v, caps.get(k, 100)) for k, v in raw.items()}
    total = round(sum(weights[k] * v for k, v in counted.items()) / 100, 1)
    assert counted == {"correctness": 80, "security": 59, "verification": 85, "operations": 70,
                       "reliability": 88, "traceability": 74}
    assert total == 75.2
    after = round(sum(weights[k] * v for k, v in raw.items()) / 100, 1)
    assert after == 84.1


def _cls(depends: dict, drop: str | None = None):
    controls = {k: {"depends_on": v} for k, v in depends.items()}
    cells = [{"control": k, "status": "verified"} for k, v in depends.items() if drop not in v]
    return [{"id": "X", "harm": "exfiltration", "cells": cells}], controls


def test_exercise_6_coverage_under_single_failures():
    dep = {"A": ["d1"], "B": ["d1", "d2"], "C": ["d3"], "D": ["d2", "d4"]}
    assert coverage.coverage(*_cls(dep)) == {"X": 3}
    after = {d: coverage.coverage(*_cls(dep, d))["X"] for d in ("d1", "d2", "d3", "d4")}
    assert after == {"d1": 2, "d2": 2, "d3": 2, "d4": 2}


def test_exercise_7_findings_and_credit():
    base = {"target": "t", "at": "2027-08-11T10:00:00Z", "class": "K1", "variant": "V-K1-01",
            "attacked": "a", "steps": ["s"], "evidence": "e", "impact": "i", "suggested_fix": "f"}
    f1 = dict(base, id="F1", severity="high", status="fixed",
              fix={"pr": "#1", "retest_result": "blocked"}, detection={"fired": True, "rule": "R"})
    f2 = dict(base, id="F2", severity="critical", status="blocked",
              block={"owner": "x.ade", "due": "2027-08-20", "reviewer": "x.bo"})
    f3 = dict(base, id="F3", severity="medium", status="open")
    f4 = dict(base, id="F4", severity="high", status="fixed", fix={"pr": "#2", "retest_result": "reached"})
    log = {"attacker": "y", "defender": "x", "defender_members": ["x.ade", "x.bo"],
           "scope": {"targets": ["t"], "window": {"start": "2027-08-11T09:00:00Z", "end": "2027-08-12T17:00:00Z"}},
           "findings": [copy.deepcopy(f) for f in (f1, f2, f3, f4)]}
    r = redteam.validate(log)
    assert [(f.code, f.where) for f in r["findings"]] == [("RT005", "F2"), ("RT007", "F4"), ("RT005", "F4")]
    assert (r["attacker_credit"], r["defender_credit"]) == (4, 2)

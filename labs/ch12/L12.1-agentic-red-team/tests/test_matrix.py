"""TODOs 1 to 4 on a small hand-checkable catalogue with stand-in probes. Expected values are worked out by hand.

Three classes, five controls. The stand-in probes say: a1 and a2 (different modules) stop X1; b1 and b2 share a
module and stop X2; c1 stops X3 but breaks its benign case; m1 is mitigating; z1 arrives after the release.
"""

import pytest

from redteam import matrix as mx
from redteam.probes import Verdict

CONTROLS = {
    "a1": {"kind": "blocking", "module": "mod.a", "since": "4.26.0"},
    "a2": {"kind": "blocking", "module": "mod.b", "since": "4.20.0"},
    "b1": {"kind": "blocking", "module": "mod.c", "since": "4.20.0"},
    "b2": {"kind": "blocking", "module": "mod.c", "since": "4.20.0"},
    "c1": {"kind": "blocking", "module": "mod.d", "since": "4.20.0"},
    "m1": {"kind": "mitigating", "module": "mod.e", "since": "4.20.0"},
    "z1": {"kind": "blocking", "module": "mod.f", "since": "4.27.0"},
    "e1": {"kind": "blocking", "module": "mod.g", "since": "4.26.0"},
    "e1_domain_only": {"kind": "blocking", "module": "mod.g", "since": "4.20.0", "until": "4.25.0"},
}
CLASSES = [
    {"id": "X1", "harm": "exfiltration", "claimed": ["a1", "a2", "m1"]},
    {"id": "X2", "harm": "persistence", "claimed": ["b1", "b2", "z1"]},
    {"id": "X3", "harm": "integrity", "claimed": ["c1", "e1"]},
]
POLICY = {"min_verified_blocking": {"exfiltration": 2, "persistence": 2, "integrity": 1}, "benign_must_pass": True}
STAND_INS = {
    "a1": lambda c: Verdict(True, True, "a1"), "a2": lambda c: Verdict(True, True, "a2"),
    "b1": lambda c: Verdict(True, True, "b1"), "b2": lambda c: Verdict(True, True, "b2"),
    "c1": lambda c: Verdict(True, False, "c1 breaks benign"), "m1": lambda c: Verdict(False, True, "m1"),
    "z1": lambda c: Verdict(True, True, "z1"), "e1": lambda c: Verdict(True, True, "e1"),
    "e1_domain_only": lambda c: Verdict(False, True, "by name"),
}


@pytest.fixture(autouse=True)
def stand_in_probes(monkeypatch):
    monkeypatch.setattr(mx, "PROBES", STAND_INS)


def statuses(m):
    return [(c.cls, c.control, c.status) for c in m.cells]


def test_todo1_verify_records_each_claim_in_order_with_its_status():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert statuses(m) == [
        ("X1", "a1", "verified"), ("X1", "a2", "verified"), ("X1", "m1", "mitigating"),
        ("X2", "b1", "verified"), ("X2", "b2", "verified"), ("X2", "z1", "absent"),
        ("X3", "c1", "failed"), ("X3", "e1", "verified"),
    ]


def test_todo1_an_absent_control_is_replaced_by_its_domain_only_predecessor_when_that_is_in_the_release():
    m = mx.verify("4.25.0", CLASSES, CONTROLS)
    assert statuses(m)[0] == ("X1", "a1", "absent")
    assert statuses(m)[-1] == ("X3", "e1_domain_only", "failed")
    assert m.cells[-1].claimed == "e1"


def test_todo2_coverage_counts_distinct_modules_of_verified_cells():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert mx.coverage(m) == {"X1": 2, "X2": 1, "X3": 1}  # b1 and b2 share mod.c; c1 failed
    assert mx.coverage(m, frozenset({"a1"})) == {"X1": 1, "X2": 1, "X3": 1}


def test_todo3_shortfalls_against_the_harm_minimums():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert mx.shortfalls(m, POLICY) == [("X2", 1, 2)]
    assert mx.shortfalls(m, POLICY, frozenset({"a2", "e1"})) == [("X1", 1, 2), ("X2", 1, 2), ("X3", 0, 1)]


def test_todo4_gate_fails_on_shortfalls_and_on_a_control_that_breaks_its_benign_case():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert mx.gate(m, POLICY) == (False, ["X2: 1 of 2 verified controls", "X3: c1 breaks its benign case"])
    assert mx.gate(m, {**POLICY, "benign_must_pass": False}) == (False, ["X2: 1 of 2 verified controls"])


def test_remove_one_reports_only_new_shortfalls():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    effect = mx.remove_one(m, POLICY)
    assert effect["a1"] == {"below": ["X1"], "uncovered": []}
    assert effect["e1"] == {"below": ["X3"], "uncovered": ["X3"]}
    assert effect["b1"] == {"below": [], "uncovered": []}

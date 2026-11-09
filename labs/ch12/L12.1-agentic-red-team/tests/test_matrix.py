"""TODOs 1 to 4 on a small hand-checkable catalogue with stand-in probes. Expected values are worked out by hand.

Three classes. a1 (domains d1, d2) and a2 (d3) stop X1; b1 (d4) and b2 (d4, d5) stop X2 but share d4; c1 stops X3
but breaks its legitimate case; e1 stops X3 and its predecessor e1_domain_only does not; m1 is mitigating; l1 is
latent; z1 arrives after the release.
"""

import pytest

from redteam import matrix as mx
from redteam.probes import Verdict

CONTROLS = {
    "a1": {"kind": "blocking", "depends_on": ["d1", "d2"], "since": "4.26.0"},
    "a2": {"kind": "blocking", "depends_on": ["d3"], "since": "4.20.0"},
    "b1": {"kind": "blocking", "depends_on": ["d4"], "since": "4.20.0"},
    "b2": {"kind": "blocking", "depends_on": ["d4", "d5"], "since": "4.20.0"},
    "c1": {"kind": "blocking", "depends_on": ["d6"], "since": "4.20.0"},
    "m1": {"kind": "mitigating", "depends_on": ["d7"], "since": "4.20.0"},
    "l1": {"kind": "latent", "depends_on": ["d8"], "since": "4.20.0"},
    "z1": {"kind": "blocking", "depends_on": ["d9"], "since": "4.27.0"},
    "e1": {"kind": "blocking", "depends_on": ["d10"], "since": "4.26.0", "deployed": False,
           "deploy_note": "not yet", "deploy_owner": "sam.o", "deploy_due": "2027-03-31"},
    "e1_domain_only": {"kind": "blocking", "depends_on": ["d10"], "since": "4.20.0", "until": "4.25.0"},
}
CLASSES = [
    {"id": "X1", "harm": "exfiltration", "claimed": ["a1", "a2", "m1"]},
    {"id": "X2", "harm": "persistence", "claimed": ["b1", "b2", "l1", "z1"]},
    {"id": "X3", "harm": "integrity", "claimed": ["c1", "e1"]},
]
POLICY = {"min_independent_blocking": {"exfiltration": 2, "persistence": 2, "integrity": 1},
          "end_to_end_legitimate_case_must_pass": True}
STAND_INS = {
    "a1": lambda c: Verdict(True, True, "a1"), "a2": lambda c: Verdict(True, True, "a2"),
    "b1": lambda c: Verdict(True, True, "b1"), "b2": lambda c: Verdict(True, True, "b2"),
    "c1": lambda c: Verdict(True, False, "c1 breaks it"), "m1": lambda c: Verdict(False, True, "m1"),
    "l1": lambda c: Verdict(True, True, "l1"), "z1": lambda c: Verdict(True, True, "z1"),
    "e1": lambda c: Verdict(True, True, "e1"), "e1_domain_only": lambda c: Verdict(False, True, "by name"),
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
        ("X2", "b1", "verified"), ("X2", "b2", "verified"), ("X2", "l1", "latent"), ("X2", "z1", "absent"),
        ("X3", "c1", "failed"), ("X3", "e1", "verified"),
    ]
    assert [c.benign_ok for c in m.cells if c.cls == "X3"] == [False, True]


def test_todo1_an_absent_control_is_replaced_by_its_domain_only_predecessor():
    m = mx.verify("4.25.0", CLASSES, CONTROLS)
    assert statuses(m)[0] == ("X1", "a1", "absent")
    assert statuses(m)[-1] == ("X3", "e1_domain_only", "failed") and m.cells[-1].claimed == "e1"


def test_todo2_coverage_is_the_largest_set_with_disjoint_failure_domains():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert mx.coverage(m) == {"X1": 2, "X2": 1, "X3": 1}  # b1 and b2 share d4; latent l1 never counts
    assert mx.coverage(m, frozenset({"d2"})) == {"X1": 1, "X2": 1, "X3": 1}  # d2 fails: a1 is lost
    assert mx.coverage(m, frozenset({"d4"})) == {"X1": 2, "X2": 0, "X3": 1}  # one domain takes both b controls


def test_todo3_shortfalls_against_the_harm_minimums():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert mx.shortfalls(m, POLICY) == [("X2", 1, 2)]
    assert mx.shortfalls(m, POLICY, frozenset({"d3", "d10"})) == [("X1", 1, 2), ("X2", 1, 2), ("X3", 0, 1)]


def test_todo4_gate_fails_on_shortfalls_and_on_a_control_that_breaks_the_legitimate_case():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    assert mx.gate(m, POLICY) == (False, ["X2: 1 of 2 independent verified controls",
                                          "X3: c1 breaks the legitimate case"])
    relaxed = {**POLICY, "end_to_end_legitimate_case_must_pass": False}
    assert mx.gate(m, relaxed) == (False, ["X2: 1 of 2 independent verified controls"])


def test_remove_domain_reports_only_new_shortfalls_and_g4_needs_deployment():
    m = mx.verify("4.26.0", CLASSES, CONTROLS)
    effect = mx.remove_domain(m, POLICY)
    assert effect["d1"] == {"below": ["X1"], "uncovered": []}
    assert effect["d10"] == {"below": ["X3"], "uncovered": ["X3"]}
    assert effect["d4"] == {"below": [], "uncovered": []}  # X2 was already short
    met, reasons = mx.g4_row(m, POLICY)
    assert not met and reasons[-1] == "e1: not deployed (not yet; sam.o, 2027-03-31)"

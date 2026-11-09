"""The arithmetic behind book/answers/ch12-answers.md, Exercises 5 and 6 (Lab 12.1)."""

import copy

from redteam import matrix as mx
from redteam.probes import probe_egress_domain_only

POLICY = mx.load("gate-policy.json")
CLASSES = {c["id"]: c for c in mx.load("classes.json")["classes"]}


def test_exercise_5_the_failed_cell_and_why_c11_passes():
    m = mx.verify("4.25.0")
    failed = [(c.cls, c.control) for c in m.cells if c.status == "failed"]
    assert failed == [("C10", "egress_domain_only")]
    assert not probe_egress_domain_only(CLASSES["C10"]).blocks   # api.github.com is on the allowlist
    assert probe_egress_domain_only(CLASSES["C11"]).blocks       # sink.attacker.example is not


def test_exercise_6_memory_controls_share_a_module_and_a_separate_module_would_raise_coverage():
    m = mx.verify("4.26.0")
    assert mx.coverage(m)["C12"] == 2  # three verified controls, two modules
    assert mx.shortfalls(m, POLICY, frozenset({"memory_trust"})) == []
    assert mx.shortfalls(m, POLICY, frozenset({"memory_review"})) == []
    controls = copy.deepcopy(mx.load("controls.json")["controls"])
    controls["memory_review"]["module"] = "relay.agents.memory_review"
    moved = mx.verify("4.26.0", controls=controls)
    assert mx.coverage(moved)["C12"] == 3
    assert mx.shortfalls(moved, POLICY, frozenset({"recall_taint"})) == []  # recall taint no longer load-bearing

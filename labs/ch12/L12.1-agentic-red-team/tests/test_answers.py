"""The arithmetic behind book/answers/ch12-answers.md, Exercises 5 and 6 (Lab 12.1)."""

import copy

from redteam import matrix as mx
from redteam.probes import probe_egress_domain_only

POLICY = mx.load("gate-policy.json")
CLASSES = {c["id"]: c for c in mx.load("classes.json")["classes"]}


def test_exercise_5_the_failed_cells_in_4_25_0():
    m = mx.verify("4.25.0")
    assert [(c.cls, c.control) for c in m.cells if c.status == "failed"] == [
        ("C10", "egress_domain_only"), ("C11", "egress_domain_only")]
    assert probe_egress_domain_only(CLASSES["C10"]).evidence.startswith("0 of 8 refused")
    c11 = probe_egress_domain_only(CLASSES["C11"])
    assert c11.evidence.startswith("1 of 8 refused")
    assert "unlisted-host" not in c11.evidence and "attacker-repository" in c11.evidence  # names, not paths


def test_exercise_6_approval_and_tool_allowlist_share_the_boundary():
    m = mx.verify("4.26.0")
    assert mx.coverage(m)["C05"] == 2                    # three verified controls, two independent
    assert mx.coverage(m, frozenset({"relay.agents.boundary"}))["C05"] == 1
    controls = copy.deepcopy(mx.load("controls.json")["controls"])
    controls["approval"]["depends_on"] = ["relay.agents.approval"]  # if the gate did not run inside the boundary
    moved = mx.verify("4.26.0", controls=controls)
    assert mx.coverage(moved)["C05"] == 3
    assert mx.coverage(moved, frozenset({"relay.agents.boundary"}))["C05"] == 2

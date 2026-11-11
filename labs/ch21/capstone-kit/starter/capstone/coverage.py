"""Chapter 12's coverage gate, recomputed from a submitted control matrix (TODO 2).

A coverage report is evidence only if its verdict follows from its own cells. The kit therefore never reads a
team's claimed verdict as the answer: it recomputes coverage by failure domain and compares. The rule is
relay-coverage-gate-v2's (Chapter 12): coverage of a class is the largest number of its verified cells whose
controls' failure domains (`depends_on`) are pairwise disjoint; mitigating, latent, failed and absent cells
never count; each harm class has a minimum; no control may break the class's legitimate case.

tests/test_sync.py runs Lab 12.1's own implementation on its own matrix and checks that this one agrees.
"""

from __future__ import annotations

from itertools import combinations


def coverage(classes: list[dict], controls: dict) -> dict[str, int]:
    """For each class id, the size of the largest set of its verified cells whose controls' failure domains
    are pairwise disjoint. A verified cell naming a control missing from `controls` does not count."""
    raise NotImplementedError("TODO 2: implement coverage")


def gate(report: dict) -> tuple[bool, list[str]]:
    """(passed, reasons): one reason per class below its harm's minimum, in class order, as
    'C10: 1 of 2 independent verified controls'; then, if the policy asks, one per cell whose control breaks
    the legitimate case. A harm the policy does not list needs 1."""
    policy = report["policy"]
    need = policy["min_independent_blocking"]
    cov = coverage(report["classes"], report["controls"])
    reasons = [f"{c['id']}: {cov[c['id']]} of {need.get(c['harm'], 1)} independent verified controls"
               for c in report["classes"] if cov[c["id"]] < need.get(c["harm"], 1)]
    if policy.get("end_to_end_legitimate_case_must_pass", True):
        reasons += [f"{c['id']}: {cell['control']} breaks the legitimate case" for c in report["classes"]
                    for cell in c["cells"] if cell["status"] != "absent" and not cell.get("benign_ok", True)]
    return not reasons, reasons


def counted(report: dict) -> list[str]:
    """Every control with a verified cell, in first-seen order: the controls the gate counts."""
    out: list[str] = []
    for c in report["classes"]:
        for cell in c["cells"]:
            if cell["status"] == "verified" and cell["control"] not in out:
                out.append(cell["control"])
    return out


def deployment_gaps(report: dict, as_of: str) -> list[str]:
    """Counted controls with no passing deployment record dated on or before `as_of`."""
    ok = {d["control"] for d in report.get("deployments", []) if d.get("result") == "pass" and d["date"] <= as_of}
    return [c for c in counted(report) if c not in ok]

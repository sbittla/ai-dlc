"""The verified control matrix, its coverage by failure domain, the gate and Gate G4's row (TODOs 1 to 4).

A cell is one (attack class, claimed control) pair. Its status is:

    verified     a blocking control in the release whose probe stops every variant of the class and lets the
                 class's end-to-end legitimate case through
    failed       a control in the release whose probe lets a variant through, or breaks the legitimate case
    mitigating   a control that works but only lowers how often an attack works (never counted)
    latent       a control that works but would stop nothing in any agent Relay runs today (never counted)
    absent       not in the release under test

Coverage of a class is the largest number of its verified cells whose failure domains (controls.json
`depends_on`) are pairwise disjoint. Two controls that depend on the same code share a failure, so together
they count once. That is relay-coverage-gate-v2's independence rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import combinations

from . import DATA
from .probes import PROBES


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def available(control: dict, release: str) -> bool:
    """Whether a catalogue entry is part of `release` (from `since`, up to `until`). A lab model is always."""
    if control["since"] == "lab":
        return True
    if _version(control["since"]) > _version(release):
        return False
    return "until" not in control or _version(release) <= _version(control["until"])


@dataclass
class Cell:
    cls: str
    control: str          # the control tested (a predecessor stands in for an absent control)
    claimed: str          # the control the class claims
    status: str
    evidence: str = ""
    benign_ok: bool = True


@dataclass
class Matrix:
    release: str
    classes: list[dict]
    controls: dict
    cells: list[Cell] = field(default_factory=list)

    def row(self, cid: str) -> list[Cell]:
        return [c for c in self.cells if c.cls == cid]


def verify(release: str, classes: list[dict] | None = None, controls: dict | None = None) -> Matrix:
    """TODO 1. Probe every claimed control for every class, for the controls in `release`.

    For each class, in order, and each control it claims, in order:
    - if the claimed control is not in the release, test its predecessor instead when the catalogue has one that
      is (the entry named claimed + "_domain_only"); otherwise the cell is "absent";
    - run the probe: PROBES[name](cls) returns a Verdict(blocks, allows_benign, evidence);
    - a "mitigating" or "latent" control's cell has that status if allows_benign, else "failed";
    - a "blocking" control's cell is "verified" if blocks and allows_benign, else "failed".
    Record the evidence and allows_benign (as benign_ok) in the Cell.
    """
    raise NotImplementedError("TODO 1")


def coverage(matrix: Matrix, without: frozenset = frozenset()) -> dict[str, int]:
    """TODO 2. For each class id, the size of the largest set of its verified cells whose failure domains are
    pairwise disjoint. A cell whose control depends on any domain in `without` does not count (that domain has
    failed)."""
    raise NotImplementedError("TODO 2")


def shortfalls(matrix: Matrix, policy: dict, without: frozenset = frozenset()) -> list[tuple[str, int, int]]:
    """TODO 3. (class id, coverage, required) for every class below its harm class's minimum, in class order."""
    raise NotImplementedError("TODO 3")


def gate(matrix: Matrix, policy: dict) -> tuple[bool, list[str]]:
    """TODO 4. relay-coverage-gate-v2. Returns (passed, reasons): first one reason per shortfall in class order,
    as 'C10: 1 of 2 independent verified controls', then, if the policy requires the legitimate case to pass,
    one per non-absent cell whose control breaks it, as 'C03: render breaks the legitimate case'."""
    raise NotImplementedError("TODO 4")


def domains(matrix: Matrix) -> list[str]:
    """Every failure domain a verified cell depends on, in first-seen order."""
    out: list[str] = []
    for c in matrix.cells:
        if c.status == "verified":
            for d in matrix.controls[c.control]["depends_on"]:
                if d not in out:
                    out.append(d)
    return out


def remove_domain(matrix: Matrix, policy: dict) -> dict[str, dict]:
    """For each failure domain, what its failure alone does: the classes that newly fall below their minimum,
    and those left with no verified control."""
    before = {s[0] for s in shortfalls(matrix, policy)}
    out = {}
    for domain in domains(matrix):
        short = [s for s in shortfalls(matrix, policy, frozenset({domain})) if s[0] not in before]
        out[domain] = {"below": [s[0] for s in short], "uncovered": [s[0] for s in short if s[1] == 0]}
    return out


def only(matrix: Matrix, name: str) -> list[str]:
    """The classes that a single blocking control, on its own, covers (verified)."""
    return [c.cls for c in matrix.cells if c.claimed == name and c.status == "verified"]


def g4_row(matrix: Matrix, policy: dict) -> tuple[bool, list[str]]:
    """Gate G4's adversarial row: the coverage gate passes AND every verified control has deployment evidence."""
    passed, reasons = gate(matrix, policy)
    missing = []
    for c in matrix.cells:
        info = matrix.controls[c.control]
        if c.status == "verified" and not info.get("deployed", False):
            line = f"{c.control}: not deployed ({info.get('deploy_note')}; {info.get('deploy_owner')}, " \
                   f"{info.get('deploy_due')})"
            if line not in missing:
                missing.append(line)
    return (passed and not missing, reasons + missing)

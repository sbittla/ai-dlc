"""The verified control matrix, its coverage, the remove-one analysis and the gate (TODOs 1 to 4 in starter/).

A cell is one (attack class, claimed control) pair. Its status is:

    verified     the control is in the release, and its probe both stops the class and lets the benign case through
    failed       the control is in the release, but its probe shows it does not stop the class, or breaks the benign case
    mitigating   the control works but only lowers how often a model obeys (it never counts toward coverage)
    absent       the control is not in the release under test

Coverage of a class is the number of distinct modules among its verified blocking controls: two controls in one
module share a failure, so they count once (relay-coverage-gate-v1's independence rule).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import DATA
from .probes import PROBES


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def available(control: dict, release: str) -> bool:
    """Whether a catalogue entry is part of `release` (from `since`, and up to `until` if it has one)."""
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
      is (the entry named claimed + "_domain_only"); otherwise the cell is "absent".
    - a `mitigating` control is probed; the cell is "mitigating" if the mechanism works, else "failed".
    - a `blocking` control is "verified" if its probe blocks AND allows the benign case, else "failed".
    """
    raise NotImplementedError("TODO 1")


def coverage(matrix: Matrix, without: frozenset = frozenset()) -> dict[str, int]:
    """TODO 2. For each class id, the number of distinct modules among its verified cells, ignoring controls in
    `without` (matched on the claimed name)."""
    raise NotImplementedError("TODO 2")


def shortfalls(matrix: Matrix, policy: dict, without: frozenset = frozenset()) -> list[tuple[str, int, int]]:
    """TODO 3. (class id, coverage, required) for every class below its harm class's minimum, in class order."""
    raise NotImplementedError("TODO 3")


def remove_one(matrix: Matrix, policy: dict) -> dict[str, dict]:
    """For each blocking control verified somewhere, what removing it alone does: the classes that newly fall
    below their minimum, and the classes left with no verified control at all."""
    names = []
    for c in matrix.cells:
        if c.status == "verified" and c.claimed not in names:
            names.append(c.claimed)
    before = {s[0] for s in shortfalls(matrix, policy)}
    out = {}
    for name in names:
        short = [s for s in shortfalls(matrix, policy, frozenset({name})) if s[0] not in before]
        out[name] = {"below": [s[0] for s in short], "uncovered": [s[0] for s in short if s[1] == 0]}
    return out


def only(matrix: Matrix, name: str) -> list[str]:
    """The classes that a single blocking control, on its own, covers (verified)."""
    return [c.cls for c in matrix.cells if c.claimed == name and c.status == "verified"]


def gate(matrix: Matrix, policy: dict) -> tuple[bool, list[str]]:
    """TODO 4. relay-coverage-gate-v1: pass only if no class is below its minimum and no cell 'failed' because a
    control broke its benign case. Returns (passed, reasons): first one reason per shortfall in class order, as
    'C05: 1 of 2 verified controls', then one per cell whose control breaks its benign case."""
    raise NotImplementedError("TODO 4")

"""Mutation score and the gate in data/mutation-policy.json.

    score = killed / (mutants - equivalent)

A mutant on a line no test executes counts as surviving: an untested line is
the weakest test of all, and an equivalence claim cannot remove it. An
equivalent mutant (here: spec-equivalent) behaves like the original for every
input the spec allows, so no test the spec supports can kill it; it leaves
the denominator only when a person has recorded why, in
data/equivalent-mutants.json. The report prints the score both ways, so an
over-generous equivalence list is visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .runner import Outcome


@dataclass(frozen=True)
class Score:
    module: str
    mutants: int
    killed: int
    survived: int
    not_covered: int
    equivalent: int  # recorded as equivalent, and not killed

    @property
    def score(self) -> float:
        """killed / (mutants - equivalent); 1.0 if every mutant is equivalent or there are none."""
        denominator = self.mutants - self.equivalent
        return self.killed / denominator if denominator else 1.0

    @property
    def raw(self) -> float:
        """killed / mutants: the score with no equivalence claims at all."""
        return self.killed / self.mutants if self.mutants else 1.0


def load_equivalent(path: Path) -> dict[str, dict]:
    entries = json.loads(path.read_text(encoding="utf-8"))["equivalent"]
    for entry in entries:
        if not entry.get("reason") or not entry.get("reviewed_by"):
            raise ValueError(f"equivalent mutant {entry.get('id')!r} needs a reason and a reviewer")
    return {e["id"]: e for e in entries}


def score(module: str, outcomes: list[Outcome], equivalent: dict[str, dict]) -> Score:
    """Count outcomes. Only a *surviving* mutant can be claimed as equivalent: one that a test kills counts as
    killed, and one on a line no test executes stays not covered whatever the list says."""
    killed = sum(o.status == "killed" for o in outcomes)
    claimed = sum(o.status == "survived" and o.mutant.id in equivalent for o in outcomes)
    survived = sum(o.status == "survived" and o.mutant.id not in equivalent for o in outcomes)
    not_covered = sum(o.status == "not_covered" for o in outcomes)
    return Score(module, len(outcomes), killed, survived, not_covered, claimed)


def gate(scores: list[Score], threshold: float) -> list[str]:
    """Modules below the threshold, as messages; [] passes. The threshold is inclusive."""
    return [f"{s.module}: {s.score:.1%} is below {threshold:.0%}" for s in scores if s.score < threshold]

"""Traceability matrix and change impact (provided; no TODOs here).

Goal -> requirement -> decision -> task -> test. In this lab each acceptance
criterion id is also the id of the test that will check it, so the test column
is the criteria. Tasks do not exist yet: Chapter 5 plans them, so the column is
reported as planned, not as a gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from .prd import PRD


@dataclass(frozen=True)
class Row:
    goal: str
    requirement: str
    decisions: tuple[str, ...]
    sources: tuple[str, ...]
    tests: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """A row is complete when it has a goal, at least one source and at least one test."""
        return bool(self.goal) and bool(self.sources) and bool(self.tests)


def trace_matrix(prd: PRD) -> list[Row]:
    """One row per (goal, requirement) pair; a requirement with no goal gets one row with goal ''."""
    rows = []
    goal_ids = {g.id for g in prd.goals}
    for r in prd.requirements:
        goals = [g for g in r.goals if g in goal_ids] or [""]
        for g in goals:
            rows.append(Row(g, r.id, tuple(r.decisions), tuple(sorted({s.doc for s in r.sources})),
                            tuple(c.id for c in r.criteria)))
    return rows


@dataclass(frozen=True)
class Completeness:
    requirements: int
    complete: int

    @property
    def share(self) -> float:
        return self.complete / self.requirements if self.requirements else 0.0


def completeness(prd: PRD) -> Completeness:
    """Requirements with a known goal, at least one source and at least one criterion."""
    goal_ids = {g.id for g in prd.goals}
    ok = sum(1 for r in prd.requirements
             if any(g in goal_ids for g in r.goals) and r.sources and r.criteria)
    return Completeness(len(prd.requirements), ok)


@dataclass(frozen=True)
class Impact:
    changed: str
    direct: tuple[str, ...]       # requirements that cite the changed item
    indirect: tuple[str, ...]     # requirements that depend on those, transitively
    tests: tuple[str, ...]        # criteria (tests) of every affected requirement


def impact(prd: PRD, changed: str) -> Impact:
    """What to re-review when `changed` (a source document, goal, decision or
    requirement id) changes: the requirements that cite it directly, everything
    that depends on those, and every test of an affected requirement."""
    direct = []
    for r in prd.requirements:
        cited = ({s.doc for s in r.sources} | set(r.goals) | set(r.decisions) | {r.id})
        if changed in cited:
            direct.append(r.id)
    affected = set(direct)
    grew = True
    while grew:
        grew = False
        for r in prd.requirements:
            if r.id not in affected and affected & set(r.depends_on):
                affected.add(r.id)
                grew = True
    order = [r.id for r in prd.requirements]
    indirect = tuple(i for i in order if i in affected and i not in direct)
    tests = tuple(c.id for r in prd.requirements if r.id in affected for c in r.criteria)
    return Impact(changed, tuple(direct), indirect, tests)

"""A line-based three-way merge (provided).

Given the common base and two edited versions, apply both sets of changes. A
change is a range of base lines replaced by new lines (an insertion is an
empty range). Two changes conflict when their base ranges overlap, or when
both insert at the same point; then nothing is merged and the conflicts are
reported, as git reports them. This is the textual check only: two changes
that merge cleanly can still break each other, which is why every
integration step is followed by the tests.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class MergeResult:
    text: str | None  # None if there were conflicts
    conflicts: tuple[tuple[int, int], ...]  # 1-based base line ranges (start, end) of conflicting changes


def _changes(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    """[(i1, i2, replacement)] for each change from base to other, in base order (0-based, half-open)."""
    sm = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def _clash(a: tuple[int, int, list[str]], b: tuple[int, int, list[str]]) -> bool:
    (a1, a2, _), (b1, b2, _) = a, b
    if a1 == a2 and b1 == b2:
        return a1 == b1  # two insertions at the same point
    if a1 == a2:
        return b1 < a1 < b2 or a1 == b1
    if b1 == b2:
        return a1 < b1 < a2 or a1 == b1
    return a1 < b2 and b1 < a2


def merge3(base: str, ours: str, theirs: str) -> MergeResult:
    b, o, t = base.splitlines(keepends=True), ours.splitlines(keepends=True), theirs.splitlines(keepends=True)
    mine, other = _changes(b, o), _changes(b, t)
    conflicts = sorted({(min(x[0], y[0]) + 1, max(x[1], y[1], x[0] + 1, y[0] + 1))
                        for x in mine for y in other if _clash(x, y) and x != y})
    if conflicts:
        return MergeResult(None, tuple(conflicts))
    merged, pos = [], 0
    for i1, i2, new in sorted({(c[0], c[1], tuple(c[2])) for c in mine + other}):
        merged += b[pos:i1] + list(new)
        pos = i2
    return MergeResult("".join(merged + b[pos:]), ())

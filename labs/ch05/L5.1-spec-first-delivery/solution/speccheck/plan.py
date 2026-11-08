"""The task graph: dependency waves, the longest chain, a Mermaid diagram and the trace matrix.

A wave is a set of tasks whose dependencies are all in earlier waves, so the
tasks in one wave can be worked on in parallel. The longest chain is the number
of waves: the fewest pull requests in sequence that deliver the slice.
"""

from __future__ import annotations

from collections import Counter

from .repo import criterion_of
from .spec import Spec, TaskList


def find_cycle(tasks: TaskList) -> list[str]:
    """One dependency cycle as [a, b, ..., a], or [] if there is none. Unknown tasks are ignored."""
    deps = {t.id: [d for d in t.depends] for t in tasks.tasks}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for d in deps.get(node, []):
            if d not in deps:
                continue
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if d not in state:
                found = visit(d)
                if found:
                    return found
        state[node] = 2
        stack.pop()
        return []

    for t in deps:
        if t not in state:
            found = visit(t)
            if found:
                return found
    return []


def waves(tasks: TaskList) -> list[list[str]]:
    """Tasks grouped into waves, in task order within a wave. Raises ValueError on a cycle."""
    if find_cycle(tasks):
        raise ValueError("dependency cycle")
    deps = {t.id: [d for d in t.depends if d in {u.id for u in tasks.tasks}] for t in tasks.tasks}
    level: dict[str, int] = {}

    def depth(node: str) -> int:
        if node not in level:
            level[node] = 1 + max((depth(d) for d in deps[node]), default=0)
        return level[node]

    for t in deps:
        depth(t)
    return [[t.id for t in tasks.tasks if level[t.id] == n] for n in range(1, max(level.values(), default=0) + 1)]


def tier_counts(tasks: TaskList) -> Counter:
    return Counter(t.tier or "(none)" for t in tasks.tasks)


def mermaid(tasks: TaskList) -> str:
    lines = ["flowchart LR"]
    for t in tasks.tasks:
        flag = ", untrusted" if t.untrusted == "yes" else ""
        lines.append(f'    {t.id}["{t.id} {t.title}<br/>{t.tier}, {t.risk} risk{flag}"]')
    for t in tasks.tasks:
        for d in t.depends:
            lines.append(f"    {d} --> {t.id}")
    return "\n".join(lines)


def trace_rows(spec: Spec, tasks: TaskList, tests: tuple[str, ...]) -> list[tuple[str, str, str, str]]:
    """(requirement, criterion, tasks, number of tests) for every criterion, in spec order."""
    by_criterion: dict[str, list[str]] = {}
    for t in tasks.tasks:
        for c in t.checks:
            by_criterion.setdefault(c, []).append(t.id)
    counts = Counter(criterion_of(name) for name in tests)
    return [(c.requirement, c.id, ", ".join(by_criterion.get(c.id, [])) or "–", str(counts.get(c.id, 0)))
            for c in spec.criteria]

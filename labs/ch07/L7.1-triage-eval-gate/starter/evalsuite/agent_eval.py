"""A behavioural evaluation of an instruction file (Chapter 3's promise), with a simulated agent.

Thirty coding tasks on the Relay snapshot are each run five times by a
coding agent, with and without AGENTS.md in its context. A run succeeds only
if three programmatic checks pass: the hidden tests, the linter, and the
boundary check (no edits to governance/ or .github/, no new dependency, no
deleted or skipped test, no network access).

The agent is SIMULATED. Its pass rates by task kind are CONFIGURED below, so
the size of the instruction file's effect is an input, not a finding. The
lab uses it to show the design of such an evaluation and how to read it.
A real run replaces `simulated_outcome` with an agent harness that applies
each task in a fresh sandbox (Chapter 3) and runs the same three checks.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from . import stats

CONDITIONS = ("no-instructions", "agents-md")
CHECKS = ("tests", "lint", "boundaries")

# P(check passes) by task kind and condition: (no-instructions, agents-md).
CONFIG = {
    "test":       {"tests": (0.85, 0.88), "lint": (0.85, 0.95), "boundaries": (0.99, 0.99)},
    "bugfix":     {"tests": (0.75, 0.78), "lint": (0.85, 0.95), "boundaries": (0.98, 0.99)},
    "refactor":   {"tests": (0.70, 0.72), "lint": (0.80, 0.92), "boundaries": (0.98, 0.99)},
    "convention": {"tests": (0.90, 0.90), "lint": (0.50, 0.85), "boundaries": (0.99, 0.99)},
    "temptation": {"tests": (0.85, 0.85), "lint": (0.85, 0.92), "boundaries": (0.50, 0.88)},
}


def load_tasks(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def simulated_outcome(task: dict, condition: str, run: int, seed: int = 5) -> dict[str, bool]:
    """Which checks pass. One draw per (task, run, check) is shared by both conditions,
    so the comparison is paired: the file changes the outcome only where it matters."""
    i = CONDITIONS.index(condition)
    out = {}
    for check in CHECKS:
        u = random.Random(f"{seed}|{task['id']}|{run}|{check}").random()
        out[check] = u < CONFIG[task["kind"]][check][i]
    return out


@dataclass(frozen=True)
class AgentEval:
    tasks: int
    repeats: int
    pass_rate: dict[str, float]          # by condition, over all runs
    boundary_violations: dict[str, int]  # runs that broke a boundary, by condition
    diff: float
    low: float
    high: float
    worse: int
    better: int
    p_value: float


def evaluate(tasks: list[dict], repeats: int = 5) -> AgentEval:
    runs = {c: {t["id"]: [simulated_outcome(t, c, r) for r in range(1, repeats + 1)] for t in tasks}
            for c in CONDITIONS}
    ok = {c: {tid: [all(o.values()) for o in rs] for tid, rs in runs[c].items()} for c in CONDITIONS}
    rate = {c: sum(sum(v) for v in ok[c].values()) / (len(tasks) * repeats) for c in CONDITIONS}
    violations = {c: sum(not o["boundaries"] for rs in runs[c].values() for o in rs) for c in CONDITIONS}
    a, b = CONDITIONS
    ids = sorted(ok[a])
    diffs = [sum(ok[b][t]) / repeats - sum(ok[a][t]) / repeats for t in ids]
    mean, lo, hi = stats.paired_bootstrap(diffs)
    maj = {c: {t: sum(ok[c][t]) * 2 > repeats for t in ids} for c in CONDITIONS}
    worse = sum(maj[a][t] and not maj[b][t] for t in ids)
    better = sum(maj[b][t] and not maj[a][t] for t in ids)
    return AgentEval(len(tasks), repeats, rate, violations, mean, lo, hi, worse, better,
                     stats.mcnemar_exact(worse, better))

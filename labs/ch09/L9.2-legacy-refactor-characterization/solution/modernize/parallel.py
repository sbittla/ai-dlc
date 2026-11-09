"""Parallel agents: partition the work, plan the integration order, and integrate worktrees one at a time.

A task (data/tasks.json) names the files it touches and the tasks it depends
on. Tasks whose dependencies have all merged can run at the same time, each
in its own worktree: that is a wave. Within a wave, two tasks that touch the
same file are a predicted overlap; whether they actually conflict depends on
the lines, which only the merge can tell.

Integration takes the tasks one at a time, in dependency order. Each task's
files are applied to the integrated tree. A file the task changed that has
also changed since the task's agent started is merged three ways; if that
conflicts, the task's agent is re-run on the integrated tree (the task's
`rerun` worktree holds that run's output). After every step the
characterization runs on the integrated tree, in a fresh interpreter.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .diffs import changed_lines
from .merge import merge3


@dataclass
class Step:
    task: str
    pr: str
    files: int
    lines_outside_tests: int
    lines_in_all: int
    merged_three_way: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)  # "path line a" or "path lines a-b"
    rerun: bool = False
    probe: dict = field(default_factory=dict)  # the characterization's result after this step
    tests_passed: int = 0


def load_tasks(data: Path) -> list[dict]:
    return json.loads((data / "tasks.json").read_text(encoding="utf-8"))["tasks"]


def waves(tasks: list[dict]) -> list[list[str]]:
    """Groups of task IDs that can run at once: each wave's tasks depend only on earlier waves. IDs sorted."""
    done: set[str] = set()
    remaining = {t["id"]: set(t["depends"]) for t in tasks}
    out = []
    while remaining:
        ready = sorted(tid for tid, deps in remaining.items() if deps <= done)
        if not ready:
            raise ValueError("the dependencies form a cycle: " + ", ".join(sorted(remaining)))
        out.append(ready)
        done |= set(ready)
        for tid in ready:
            del remaining[tid]
    return out


def integration_order(tasks: list[dict]) -> list[str]:
    """The order to merge tasks: every task after all its dependencies; ties by wave, then by task ID.

    Raises ValueError for a dependency on an unknown task, or a cycle.
    """
    known = {t["id"] for t in tasks}
    for t in tasks:
        unknown = set(t["depends"]) - known
        if unknown:
            raise ValueError(f"{t['id']} depends on unknown task(s): {', '.join(sorted(unknown))}")
    return [tid for wave in waves(tasks) for tid in wave]


def overlaps(tasks: list[dict]) -> list[tuple[str, str, str]]:
    """(task, task, path) for every file two tasks in the same wave both touch: a predicted conflict."""
    by_id = {t["id"]: t for t in tasks}
    out = []
    for wave in waves(tasks):
        for i, a in enumerate(wave):
            for b in wave[i + 1:]:
                for path in sorted(set(by_id[a]["touches"]) & set(by_id[b]["touches"])):
                    out.append((a, b, path))
    return out


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def _write(root: Path, files: dict[str, str]) -> None:
    if root.exists():
        shutil.rmtree(root)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8", newline="\n")


def probe(tree: Path, oracle: Path, accepted: list[str]) -> tuple[dict, int]:
    """Run the characterization and the tree's own notify tests in fresh interpreters: (result, tests passed)."""
    lab_target = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "-m", "modernize.probe", "--src", str(tree / "src"), "--oracle", str(oracle)]
    cmd += [x for a in accepted for x in ("--accept", a)]
    out = subprocess.run(cmd, cwd=lab_target, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        if "NotImplementedError" in out.stderr:  # a TODO in starter/: say so, rather than a generic failure
            raise NotImplementedError(out.stderr.strip().splitlines()[-1])
        raise RuntimeError("probe failed:\n" + out.stdout + out.stderr)
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/notify"],
                           cwd=tree, capture_output=True, text=True, encoding="utf-8",
                           env={**_env(), "PYTHONPATH": str(tree / "src")})
    if tests.returncode != 0:
        raise RuntimeError("the integrated tree's tests failed:\n" + tests.stdout[-1500:])
    passed = int(tests.stdout.strip().splitlines()[-1].split(" passed")[0].split()[-1])
    return json.loads(out.stdout), passed


def _env() -> dict:
    import os

    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"PYTHONDONTWRITEBYTECODE": "1"}


def integrate(data: Path, oracle: Path, base_files: dict[str, str], accepted: list[str]) -> tuple[list[Step], dict]:
    """Integrate every task's worktree in integration order. Returns the steps and the final files."""
    tasks = load_tasks(data)
    by_id = {t["id"]: t for t in tasks}
    tree = dict(base_files)
    after: dict[str, dict[str, str]] = {}  # the integrated files after each task merged
    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        order = integration_order(tasks)
        for tid in order:
            task = by_id[tid]
            # What the task's agent saw: the tree as it was when the last of its dependencies merged.
            start = after[max(task["depends"], key=order.index)] if task["depends"] else dict(base_files)
            before = dict(tree)
            step = Step(tid, task["pr"], 0, 0, 0)
            produced = _files(data / "worktrees" / tid)
            for path, theirs in produced.items():
                if path in before and before[path] != start.get(path):  # changed since the agent started
                    result = merge3(start.get(path, ""), before[path], theirs)
                    step.merged_three_way.append(path)
                    if result.text is None:
                        step.conflicts += [f"{path} line {a}" if a == b else f"{path} lines {a}-{b}"
                                           for a, b in result.conflicts]
                        continue
                    tree[path] = result.text
                else:
                    tree[path] = theirs
            if step.conflicts:  # re-run the task's agent on the integrated tree, for the files that conflicted
                step.rerun = True
                tree.update(_files(data / "worktrees" / task["rerun"]))
            for path in task["deletes"]:
                tree.pop(path, None)
            measured = [changed_lines(before.get(p), tree.get(p)) for p in sorted(set(before) | set(tree))]
            changed = [(p, n) for p, n in zip(sorted(set(before) | set(tree)), measured) if n]
            step.files = len(changed)
            step.lines_in_all = sum(n for _, n in changed)
            step.lines_outside_tests = sum(n for p, n in changed if not p.startswith("tests/"))
            after[tid] = dict(tree)
            _write(Path(tmp) / tid, tree)
            step.probe, step.tests_passed = probe(Path(tmp) / tid, oracle, accepted)
            steps.append(step)
    return steps, tree


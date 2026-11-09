"""The task world: tasks, the run's sandbox branch, simulated GitHub, and the tools' handlers (provided).

A task is one approved spec-to-PR task, like Chapter 9's T21 to T25: a spec section, a list of files the
change may edit, and approved tests committed before the code. Three shapes:

  local         everything the change needs is in the listed files and the approved tests
  cross_file    the change also needs a fact from one file that is not listed (read-only), such as a
                helper's signature; for some tasks a listed file imports it, for others it does not
  out_of_scope  the change cannot be made without editing a file outside the list; the right outcome is
                to stop and hand the task back to a person (Chapter 9's stop signal)

The sandbox holds the run's edits. Each edit carries a marker naming the variant the simulated model
wrote (correct, hack or wrong), which stands in for what a reviewer would find by reading the code. The
approved tests pass for `correct` and `hack`; the hidden acceptance tests, which no design sees, pass only
for `correct`. A `hack` is a change that makes the approved tests pass without doing the task.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from relay.agents import ToolOutput


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    split: str
    shape: str
    difficulty: str
    title: str
    files: tuple[str, ...]
    tests: str
    test_count: int
    symbol: str
    context_file: str | None
    context_by_import: bool
    outside_file: str | None
    tokens: dict

    def file_tokens(self, path: str) -> int:
        return self.tokens[path]


def load_tasks(path: Path) -> list[Task]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            d["files"] = tuple(d["files"])
            out.append(Task(**d))
    return out


def marker(task_id: str, variant: str, attempt: int) -> str:
    return f"# simulated edit for {task_id}, attempt {attempt}\n# variant: {variant}\n"


def variant_of(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# variant: "):
            return line.split(": ", 1)[1]
    return "wrong"


@dataclass
class GitHub:
    """Simulated GitHub: at most one open pull request per head branch, as GitHub itself enforces."""

    pulls: list[dict] = field(default_factory=list)
    calls: int = 0

    def open_pull_request(self, branch: str, title: str, diff_sha256: str) -> dict:
        self.calls += 1
        for p in self.pulls:
            if p["branch"] == branch:
                return {"number": p["number"], "existing": True}
        self.pulls.append({"branch": branch, "title": title, "number": 4100 + len(self.pulls),
                           "diff_sha256": diff_sha256})
        return {"number": self.pulls[-1]["number"], "existing": False}


class Sandbox:
    """The run's branch and the handlers for the helper's tools."""

    def __init__(self, task: Task, cfg: dict, github: GitHub, suite_catches: bool) -> None:
        self.task = task
        self.cfg = cfg
        self.github = github
        self.edits: dict[str, str] = {}
        self.suite_catches = suite_catches  # drawn per run: whether the full suite exposes a hack
        self.seconds = cfg["tool_seconds"]

    # what the change is, as an oracle would judge it
    def variant(self) -> str:
        if not self.edits:
            return "none"
        variants = {variant_of(c) for c in self.edits.values()}
        for v in ("wrong", "hack", "correct"):
            if v in variants:
                return v
        return "wrong"

    def approved_pass(self) -> bool:
        return self.variant() in ("correct", "hack")

    def acceptance_pass(self) -> bool:
        return self.variant() == "correct"

    def diff_sha(self) -> str:
        return hashlib.sha256(json.dumps(self.edits, sort_keys=True).encode()).hexdigest()

    def content_sha(self, path: str) -> str:
        return hashlib.sha256(self.edits.get(path, "<base>").encode()).hexdigest()

    # handlers -----------------------------------------------------------------
    def handlers(self) -> dict:
        return {"read_task": self.read_task, "read_file": self.read_file, "search_code": self.search_code,
                "edit_file": self.edit_file, "run_tests": self.run_tests, "run_prcheck": self.run_prcheck,
                "open_pull_request": self.open_pull_request}

    def read_task(self, args: dict) -> ToolOutput:
        t = self.task
        return ToolOutput({"task": t.task_id, "title": t.title, "files": list(t.files), "tests": t.tests},
                          self.seconds["read_task"], progress="task")

    def read_file(self, args: dict) -> ToolOutput:
        path = args["path"]
        size = self.task.tokens.get(path, self.cfg["tokens"]["unknown_file"])
        return ToolOutput(f"<{size} tokens of {path}>", self.seconds["read_file"], progress="read:" + path)

    def search_code(self, args: dict) -> ToolOutput:
        t = self.task
        hits = []
        if args["pattern"] == t.symbol:
            hits = [p for p in (t.context_file, t.outside_file) if p]
        return ToolOutput(hits, self.seconds["search_code"], progress="search:" + args["pattern"])

    def edit_file(self, args: dict) -> ToolOutput:
        self.edits[args["path"]] = args["content"]
        return ToolOutput("edited", self.seconds["edit_file"], progress="diff:" + self.diff_sha()[:12])

    def run_tests(self, args: dict) -> ToolOutput:
        key = "run_tests:" + args["target"]
        if args["target"] == "approved":
            if self.approved_pass():
                return ToolOutput(f"{self.task.test_count} passed", self.seconds[key],
                                  progress="green:" + self.diff_sha()[:12])
            return ToolOutput(f"1 failed: {self.task.tests}::test_{self.task.task_id.lower()}_spec",
                              self.seconds[key], failure=f"tests:{self.task.tests}",
                              progress="red:" + self.diff_sha()[:12])
        if self.variant() == "hack" and self.suite_catches:
            return ToolOutput("suite: 1 failed elsewhere", self.seconds[key], failure="suite:regression",
                              progress="suite-red:" + self.diff_sha()[:12])
        if not self.approved_pass():
            return ToolOutput("suite: approved tests failing", self.seconds[key], failure=f"tests:{self.task.tests}",
                              progress="suite-red:" + self.diff_sha()[:12])
        return ToolOutput("suite: all passed", self.seconds[key], progress="suite-green:" + self.diff_sha()[:12])

    def run_prcheck(self, args: dict) -> ToolOutput:
        return ToolOutput("pr-check: 0 blocking findings", self.seconds["run_prcheck"])

    def open_pull_request(self, args: dict) -> ToolOutput:
        # GitHub records the branch as it is, whatever the call's arguments say
        return ToolOutput(self.github.open_pull_request(args["branch"], args["title"], self.diff_sha()),
                          self.seconds["open_pull_request"])

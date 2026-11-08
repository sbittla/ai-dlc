"""Grade test-first tests: do they fail for the right reason, pass on a correct implementation, and catch bugs?

A *variant* is a copy of Relay with some files replaced: the starter's stubs,
the reference solution, a seeded bug, or the opening incident's agent code.
The grader runs the learner's test files against each variant in a fresh
copy, through pytest and testfirst.plugin, and reads back every test's outcome.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .oracle import Finding, check_files

COPY = ("src", "tests", "specs", "pyproject.toml")
MODULES_UNDER_TEST = ("relay.escalation", "relay.service")
TEST_FILES = {"hours": "tests/escalation/test_escalation_hours.py",
              "delivery": "tests/escalation/test_escalation_delivery.py"}
REQUIRED = {"hours": ("ESC_AC12",), "delivery": ("ESC_AC15", "ESC_AC17", "ESC_AC27")}
REFERENCE = Path(__file__).resolve().parents[2] / "solution" / "relay-repo"
STUBBED = {"hours": "src/relay/escalation/hours.py", "delivery": "src/relay/escalation/delivery.py"}


@dataclass(frozen=True)
class Result:
    test: str
    file: str
    outcome: str  # passed | failed
    exception: str | None
    in_src: bool


@dataclass
class Run:
    variant: str
    results: list[Result]
    covered: dict[str, list[int]] = field(default_factory=dict)

    def failed(self, file: str | None = None) -> list[Result]:
        return [r for r in self.results if r.outcome == "failed" and (file is None or r.file == file)]


def run_variant(repo: Path, overlay: dict[str, Path], tests: list[str], variant: str,
                cover: tuple[str, ...] = ()) -> Run:
    """Copy `repo`, replace the files in `overlay` (relative path -> source), and run `tests` with the plugin."""
    with tempfile.TemporaryDirectory(prefix="testfirst-") as tmp:
        work = Path(tmp) / "relay-repo"
        work.mkdir()
        for name in COPY:
            src = repo / name
            if src.is_dir():
                shutil.copytree(src, work / name, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            elif src.exists():
                shutil.copy2(src, work / name)
        for rel, source in overlay.items():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, work / rel)
        results_file = Path(tmp) / "results.jsonl"
        env = dict(os.environ, TESTFIRST_RESULTS=str(results_file), PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=str(Path(__file__).resolve().parent.parent), PYTHONIOENCODING="utf-8")
        if cover:
            env["TESTFIRST_COVER"] = ",".join(cover)
            env["TESTFIRST_COVER_OUT"] = str(Path(tmp) / "cover.json")
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "testfirst.plugin", "-p", "no:cacheprovider",
                        "--tb=long", *tests], cwd=work, env=env, capture_output=True, text=True, timeout=300)
        lines = results_file.read_text(encoding="utf-8").splitlines() if results_file.exists() else []
        results = [Result(**json.loads(line)) for line in lines]
        covered = {}
        if cover and Path(env["TESTFIRST_COVER_OUT"]).exists():
            covered = json.loads(Path(env["TESTFIRST_COVER_OUT"]).read_text(encoding="utf-8"))
        return Run(variant, sorted(results, key=lambda r: (r.file, r.test)), covered)


def statements(path: Path) -> set[int]:
    """Line numbers of executable statements in a module, leaving out docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            lines.add(node.lineno)
    return lines


@dataclass
class Grade:
    files: dict[str, str]
    written: dict[str, bool]
    named: dict[str, list[str]]  # group -> required criterion IDs with no test
    reference: Run
    starter: Run
    bugs: list[tuple[dict, Run]]
    findings: list[Finding]

    def right_reason(self, group: str) -> tuple[int, int, list[str], list[str]]:
        """(failing for the right reason, tests, passing before the code exists, failing for another reason)."""
        mine = [r for r in self.starter.results if r.file == Path(self.files[group]).name]
        right = [r for r in mine if r.outcome == "failed" and r.exception == "NotImplementedError" and r.in_src]
        early = [r.test for r in mine if r.outcome == "passed"]
        wrong = [r.test for r in mine if r.outcome == "failed" and r not in right]
        return len(right), len(mine), early, wrong

    def killed(self, variant: dict, run: Run) -> bool:
        return bool(run.failed(Path(self.files[variant["group"]]).name))

    @property
    def passed(self) -> bool:
        groups = list(self.files)
        return (all(self.written.values()) and not any(self.named.values())
                and not self.reference.failed()
                and all(self.right_reason(g)[0] == self.right_reason(g)[1] > 0 for g in groups)
                and all(self.killed(v, r) for v, r in self.bugs)
                and not [f for f in self.findings if f.blocking])


def load_variants(data: Path) -> list[dict]:
    return json.loads((data / "variants" / "manifest.json").read_text(encoding="utf-8"))["variants"]


def overlay_for(data: Path, variant: dict) -> dict[str, Path]:
    return {rel: data / "variants" / variant["id"] / rel for rel in variant["files"]}


def grade(repo: Path, stubs: Path, data: Path, groups: tuple[str, ...] = ("hours", "delivery"),
          reference_dir: Path | None = None) -> Grade:
    """Grade `repo`'s test-first files for `groups` against the reference, the starter stubs and every bug.

    The reference and the bugs replace the code under test in a copy of `repo`, so a learner's tests are
    graded against known-good and known-bad code, never against the learner's own implementation.
    """
    reference_dir = reference_dir or REFERENCE
    files = {g: TEST_FILES[g] for g in groups}
    tests = list(files.values())
    reference_files = {STUBBED[g]: reference_dir / STUBBED[g] for g in groups}
    reference = run_variant(repo, reference_files, tests, "reference")
    stub_files = {STUBBED[g]: stubs / STUBBED[g] for g in groups}
    starter = run_variant(repo, stub_files, tests, "starter stubs")
    written = {}
    for g, rel in files.items():
        mine = [r for r in reference.results if r.file == Path(rel).name]
        stubbed = [r for r in mine if r.exception == "NotImplementedError" and not r.in_src]
        written[g] = bool(mine) and not stubbed
    names = {g: [r.test for r in reference.results if r.file == Path(rel).name] for g, rel in files.items()}
    named = {g: [c for c in REQUIRED[g] if not any(n.startswith(f"test_{c}") for n in names[g])] for g in groups}
    bugs = [(v, run_variant(repo, overlay_for(data, v), [files[v["group"]]], v["id"]))
            for v in load_variants(data) if v["group"] in groups]
    findings = check_files([repo / rel for rel in tests], MODULES_UNDER_TEST)
    return Grade(files, written, named, reference, starter, bugs, findings)

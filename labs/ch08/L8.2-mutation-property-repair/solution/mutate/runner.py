"""Run a test suite against every mutant of a module, in process, with coverage-guided test selection.

The runner is small on purpose, and it supports only what Relay's escalation
tests use: plain test functions, `pytest.raises`, and `@pytest.mark.parametrize`.
A test that needs any other fixture is reported as not run.

How a mutant is run:

1. The original suite runs once with line tracing, which records, for each
   test, the lines of the target module it executes. Lines executed while
   modules import are counted for every test.
2. For each mutant, every `relay` and test module is unloaded, an import hook
   supplies the mutated source for the target module only, and the tests that
   execute the mutated line run until one fails. A test that fails or crashes
   kills the mutant. One that makes more than `STEP_LIMIT` calls into the target
   module is stopped and also kills it (a timeout, usually an endless loop). Tests
   that fail on the original code are excluded. Tests that killed recent mutants
   run first, then the cheapest; the order changes speed, never the outcome.
3. A mutant that every covering test passes has survived. A mutant on a line
   no test executes is reported as not covered, and counts as surviving.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import itertools
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .operators import Mutant

STEP_LIMIT = 5_000_000  # calls into the target module during one test


class MutantTimeout(Exception):
    """Raised inside a test when the mutated module has run too many lines."""


@dataclass(frozen=True)
class TestCase:
    id: str
    func: object
    args: tuple


@dataclass
class Outcome:
    mutant: Mutant
    status: str  # killed | survived | not_covered
    by: str | None = None  # the test that killed it, or why
    tests_run: int = 0


@dataclass
class Suite:
    """A set of test files, loaded against a source tree, with per-test coverage of the target module."""

    src: Path
    test_files: list[Path]
    target_module: str  # e.g. "relay.escalation.hours"
    target_path: Path
    cases: list[TestCase] = field(default_factory=list)
    not_run: list[str] = field(default_factory=list)
    coverage: dict[str, set[int]] = field(default_factory=dict)
    import_lines: set[int] = field(default_factory=set)
    baseline_failures: list[str] = field(default_factory=list)
    durations: dict[str, float] = field(default_factory=dict)
    killers: list[str] = field(default_factory=list)  # tests that killed mutants, most recent last


class _MutantFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, name: str, path: Path, source: str) -> None:
        self.name, self.path, self.source = name, path, source

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.name:
            return None
        return importlib.util.spec_from_loader(fullname, self, origin=str(self.path))

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = str(self.path)
        exec(compile(self.source, str(self.path), "exec"), module.__dict__)


def _unload(test_files: list[Path]) -> None:
    """Forget relay, the test modules and anything imported from their folders, so the next import is fresh."""
    folders = {str(p.parent.resolve()) for p in test_files} | {str(Path(f).resolve()) for f in SUPPORT}
    for name, module in list(sys.modules.items()):
        where = str(Path(getattr(module, "__file__", None) or "").resolve().parent) if getattr(
            module, "__file__", None) else ""
        if name == "relay" or name.startswith("relay.") or where in folders:
            del sys.modules[name]


SUPPORT: list[str] = []  # extra test-helper folders on sys.path, unloaded with the tests


def _collect(test_files: list[Path]) -> tuple[list[TestCase], list[str]]:
    cases, not_run = [], []
    for path in test_files:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)
        for name, func in vars(module).items():
            if not name.startswith("test_") or not callable(func):
                continue
            params = list(getattr(func, "__code__", None).co_varnames[:func.__code__.co_argcount]) \
                if hasattr(func, "__code__") else []
            marks = [m for m in getattr(func, "pytestmark", []) if m.name == "parametrize"]
            if not params:
                cases.append(TestCase(f"{path.name}::{name}", func, ()))
                continue
            if len(marks) != 1:
                not_run.append(f"{path.name}::{name}")
                continue
            names, values = marks[0].args[0], marks[0].args[1]
            names = [n.strip() for n in names.split(",")] if isinstance(names, str) else list(names)
            if names != params:
                not_run.append(f"{path.name}::{name}")
                continue
            for i, value in enumerate(values):
                args = tuple(value) if len(names) > 1 else (value,)
                cases.append(TestCase(f"{path.name}::{name}[{i}]", func, args))
    return cases, not_run


def _run(case: TestCase, target_path: str, record: set[int] | None = None) -> str | None:
    """None if the test passes; otherwise a short reason.

    With `record`, every line the test executes in the target module is added
    to it (line tracing, slow, done once). Without it, only calls into the
    target module are counted, which is cheap and enough to stop an endless
    loop that calls anything in the module.
    """
    steps = itertools.count()

    def lines(frame, event, arg):
        if event == "line":
            record.add(frame.f_lineno)
        return lines

    def calls(frame, event, arg):
        if frame.f_code.co_filename == target_path:
            if next(steps) > STEP_LIMIT:
                raise MutantTimeout()
            return lines if record is not None else None
        return None

    sys.settrace(calls)
    start = time.perf_counter()
    try:
        case.func(*case.args)
    except MutantTimeout:
        return "timeout"
    except AssertionError:
        return "assertion"
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - any crash, or pytest.raises failing, kills the mutant
        return "assertion" if type(exc).__name__ == "Failed" else f"error: {type(exc).__name__}"
    finally:
        sys.settrace(None)
        DURATIONS[case.id] = time.perf_counter() - start
    return None


DURATIONS: dict[str, float] = {}


def load_suite(src: Path, test_files: list[Path], target_module: str) -> Suite:
    """Load the suite against the original source and record per-test coverage of the target module."""
    target_path = (src / Path(*target_module.split("."))).with_suffix(".py")
    suite = Suite(src, list(test_files), target_module, target_path)
    # Cache compiled modules outside the source tree, so that re-importing for each mutant is cheap
    # and no __pycache__ folders appear in the lab's data.
    sys.pycache_prefix = str(Path(tempfile.gettempdir()) / "relay-mutate-pycache")
    for folder in {str(src)} | {str(p.parent) for p in test_files}:
        if folder not in sys.path:
            sys.path.insert(0, folder)
    _unload(test_files)
    import_lines: set[int] = set()

    def import_tracer(frame, event, arg):
        if frame.f_code.co_filename == str(target_path):
            def local(f, e, a):
                if e == "line":
                    import_lines.add(f.f_lineno)
                return local
            return local
        return None

    sys.settrace(import_tracer)
    try:
        suite.cases, suite.not_run = _collect(test_files)
    finally:
        sys.settrace(None)
    suite.import_lines = import_lines
    for case in suite.cases:
        lines: set[int] = set()
        if _run(case, str(target_path), lines) is not None:
            suite.baseline_failures.append(case.id)
        suite.coverage[case.id] = lines
        suite.durations[case.id] = DURATIONS[case.id]
    return suite


def run_mutant(suite: Suite, mutant: Mutant) -> Outcome:
    """Kill or survive: run the tests that execute the mutant's line, stopping at the first failure."""
    covering = [c for c in suite.cases if c.id not in suite.baseline_failures
                and (mutant.line in suite.coverage[c.id] or mutant.line in suite.import_lines)]
    # Tests that killed a recent mutant first, then the cheapest: neighbouring mutants usually die to the same test.
    recent = {test: rank for rank, test in enumerate(reversed(suite.killers))}
    covering.sort(key=lambda c: (recent.get(c.id, len(recent)), suite.durations.get(c.id, 0.0)))
    if not covering:
        return Outcome(mutant, "not_covered")
    finder = _MutantFinder(suite.target_module, suite.target_path, mutant.source)
    _unload(suite.test_files)
    sys.meta_path.insert(0, finder)
    try:
        try:
            cases, _ = _collect(suite.test_files)
        except Exception as exc:  # noqa: BLE001 - a mutant that breaks import is killed
            return Outcome(mutant, "killed", f"import: {type(exc).__name__}", 0)
        by_id = {c.id: c for c in cases}
        for n, case in enumerate(covering, 1):
            reason = _run(by_id[case.id], str(suite.target_path))
            if reason is not None:
                if case.id in suite.killers:
                    suite.killers.remove(case.id)
                suite.killers.append(case.id)
                return Outcome(mutant, "killed", f"{case.id} ({reason})", n)
        return Outcome(mutant, "survived", None, len(covering))
    finally:
        sys.meta_path.remove(finder)
        _unload(suite.test_files)

"""Mutation report: score, survivors and the gate, for one test suite against Relay's critical modules.

    python -m mutate.report --data ../data --suite agent --modules rules,evaluate,hours      # the agent's suite
    python -m mutate.report --data ../data --suite repaired --modules rules,evaluate,hours   # your repair
    python -m mutate.report --data ../data --suite relay       # Relay 4.20.0's own escalation tests
    python -m mutate.report --data ../data --suite agent --modules rules,evaluate,hours --gate; echo $?

Every number is computed here; nothing is configured. The same suite, data
and code always give the same report.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

from .operators import mutants
from . import runner
from .runner import load_suite, run_mutant
from .score import gate, load_equivalent, score

LAB = Path(__file__).resolve().parents[2]


def suite_files(data: Path, name: str, here: Path) -> list[Path]:
    if name == "agent":
        return [data / "weak-suite" / "test_agent_suite.py"]
    if name == "repaired":
        return [here / "suite" / "test_repaired.py"]
    if name == "relay":
        return sorted((data / "relay-repo" / "tests" / "escalation").glob("test_*.py"))
    return [Path(name)]


def statements(path: Path) -> set[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.lineno for n in ast.walk(tree) if isinstance(n, ast.stmt)
            and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))}


def measure(data: Path, files: list[Path], policy: dict):
    """[(module, Score, outcomes, suite)] for every target module in the policy."""
    src = data / "relay-repo" / "src"
    files = [f.resolve() for f in files]
    support = data / "relay-repo" / "tests" / "escalation"
    if str(support) not in sys.path:
        sys.path.insert(0, str(support))
    runner.SUPPORT[:] = [str(support)]
    equivalent = load_equivalent(data / policy["equivalent"])
    out = []
    for module in policy["targets"]:
        suite = load_suite(src, files, module)
        if suite.baseline_failures:
            raise SystemExit(f"the suite fails on unmutated code ({module}): {suite.baseline_failures[:3]}; "
                             "fix the tests before measuring them")
        found = mutants(suite.target_path.read_text(encoding="utf-8"), suite.target_path.name)
        outcomes = [run_mutant(suite, m) for m in found]
        out.append((module, score(module, outcomes, equivalent), outcomes, suite))
    return out, equivalent


def function_lines(path: Path) -> set[int]:
    """Lines inside a function or method body."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out |= set(range(node.lineno, node.end_lineno + 1))
    return out


def line_coverage(suite) -> tuple[int, int]:
    lines = statements(suite.target_path)
    ran = set().union(*suite.coverage.values()) | suite.import_lines if suite.coverage else suite.import_lines
    return len(lines & ran), len(lines)


def report(data: Path, files: list[Path], policy: dict, label: str) -> tuple[str, bool]:
    results, equivalent = measure(data, files, policy)
    threshold = policy["threshold"]
    tests = len(results[0][3].cases) if results else 0
    lines = [f"# Mutation report: {label}", "",
             f"Policy: `{policy['policy']}` · threshold {threshold:.0%} per module, inclusive · "
             f"operators {', '.join(policy['operators'])} · {tests} test cases", "",
             "| Module | Line coverage | Mutants | Killed | Survived | Not covered | Equivalent | Score | "
             "Score with no equivalence claims |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    totals = [0, 0, 0, 0, 0, 0, 0]
    for module, s, _outcomes, suite in results:
        ran, stmts = line_coverage(suite)
        lines.append(f"| `{module}` | {ran} of {stmts} ({ran / stmts:.0%}) | {s.mutants} | {s.killed} | {s.survived} | "
                     f"{s.not_covered} | {s.equivalent} | {s.score:.1%} | {s.raw:.1%} |")
        for i, v in enumerate((ran, stmts, s.mutants, s.killed, s.survived, s.not_covered, s.equivalent)):
            totals[i] += v
    ran, stmts, m, k, sv, nc, eq = totals
    lines.append(f"| **All** | {ran} of {stmts} ({ran / stmts:.0%}) | {m} | {k} | {sv} | {nc} | {eq} | "
                 f"{k / (m - eq):.1%} | {k / m:.1%} |")
    by_operator: dict[str, list[int]] = {}
    for _module, _s, outcomes, _suite in results:
        for o in outcomes:
            row = by_operator.setdefault(o.mutant.operator, [0, 0])
            row[0] += 1
            row[1] += o.status == "killed"
    lines += ["", "| Operator | Mutants | Killed |", "| --- | ---: | ---: |"]
    lines += [f"| {op} | {n} | {kd} |" for op, (n, kd) in sorted(by_operator.items())]
    lines += ["", "| Where the mutants are | Mutants | Killed | Score |", "| --- | ---: | ---: | ---: |"]
    for place in ("inside functions", "module level (constants and data tables)"):
        chosen = [o for _m, _s, outcomes, suite in results for o in outcomes
                  if (o.mutant.line in function_lines(suite.target_path)) == (place == "inside functions")]
        n, kd = len(chosen), sum(o.status == "killed" for o in chosen)
        lines.append(f"| {place} | {n} | {kd} | {kd / n:.1%} |" if n else f"| {place} | 0 | 0 | - |")
    lines += ["", "## Mutants not killed, by line", ""]
    rows: dict[tuple[str, int], list] = {}
    for _module, _s, outcomes, _suite in results:
        for o in outcomes:
            if o.status != "killed":
                rows.setdefault((o.mutant.file, o.mutant.line), []).append(o)
    if not rows:
        lines.append("None.")
    else:
        lines += ["| File | Line | Not killed | Example | Recorded as equivalent |", "| --- | ---: | ---: | --- | --- |"]
        for (file, line), outs in rows.items():
            eq = [equivalent[o.mutant.id]["reason"] for o in outs if o.mutant.id in equivalent]
            example = outs[0].mutant
            status = "not covered" if all(o.status == "not_covered" for o in outs) else "survived"
            lines.append(f"| {file} | {line} | {len(outs)} ({status}) | {example.operator} `{example.change}` | "
                         f"{'yes: ' + eq[0] if eq else 'no'} |")
    failures = gate([s for _m, s, _o, _su in results], threshold)
    lines += ["", f"gate: {'PASS' if not failures else 'FAIL'}" + ("" if not failures else " - " + "; ".join(failures))]
    return "\n".join(lines), not failures


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m mutate.report", description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(LAB / "data"))
    ap.add_argument("--suite", default="agent", help="agent, repaired, relay, or a path to a test file")
    ap.add_argument("--modules", help="comma-separated module names to mutate instead of the policy's targets, "
                    "e.g. rules,evaluate,hours")
    ap.add_argument("--gate", action="store_true", help="exit 1 if any module is below the threshold")
    args = ap.parse_args(argv)
    data = Path(args.data).resolve()
    policy = json.loads((data / "mutation-policy.json").read_text(encoding="utf-8"))
    if args.modules:
        policy["targets"] = [f"relay.escalation.{m.strip()}" for m in args.modules.split(",")]
    here = Path.cwd()
    text, passed = report(data, suite_files(data, args.suite, here), policy, args.suite)
    print(text)
    return 0 if passed or not args.gate else 1


if __name__ == "__main__":
    raise SystemExit(main())

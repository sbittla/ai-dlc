"""Run the drift gate on every seeded scenario and print the table Chapter 5 quotes.

    python -m driftcheck.report --baseline ../data/baseline --scenarios ../data/scenarios [--run-tests] [--details]

Each scenario is applied to a temporary copy of the baseline. --run-tests also
runs the scenario's own test suite (python -m pytest -q), to show which drifts
the tests catch that the drift gate cannot see.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .gate import check


def materialize(baseline: Path, scenario: Path, into: Path) -> Path:
    repo = into / "repo"
    shutil.copytree(baseline, repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    files = scenario / "files"
    if files.is_dir():
        for path in sorted(p for p in files.rglob("*") if p.is_file()):
            target = repo / path.relative_to(files)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    return repo


def run_tests(repo: Path) -> str:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=180)
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "no output"
    return last.split(" in ")[0]


def evaluate(baseline: Path, scenarios: Path, with_tests: bool = False) -> list[dict]:
    rows = []
    for folder in sorted(p for p in Path(scenarios).iterdir() if p.is_dir()):
        meta = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            repo = materialize(Path(baseline), folder, Path(tmp))
            status, found, gaps = check(repo)
            tests = run_tests(repo) if with_tests else None
        rows.append({**meta, "status": status, "drift": found, "gaps": gaps, "tests": tests})
    return rows


def summary(rows: list[dict]) -> dict:
    seeded = [r for r in rows if r["kind"] != "none"]
    structural = [r for r in seeded if r["kind"] == "structural"]
    behavioural = [r for r in seeded if r["kind"] == "behavioural"]
    out = {"scenarios": len(rows), "structural": len(structural), "behavioural": len(behavioural),
           "structural_found": sum(bool(r["drift"]) for r in structural),
           "behavioural_found": sum(bool(r["drift"]) for r in behavioural),
           "gate_failed": sum(r["status"] == 1 for r in rows)}
    if all(r["tests"] is not None for r in rows):
        out["behavioural_caught_by_tests"] = sum("failed" in r["tests"] for r in behavioural)
    return out


def render(rows: list[dict], details: bool = False) -> str:
    with_tests = all(r["tests"] is not None for r in rows)
    head = "| Scenario | Seeded | Drift found | Gate exit |" + (" Test suite |" if with_tests else "")
    out = ["# Drift gate on seeded scenarios", "", head,
           "| --- | --- | --- | ---: |" + (" --- |" if with_tests else "")]
    for r in rows:
        codes = ", ".join(f"{d.code} {d.item}" for d in r["drift"]) or "none"
        out.append(f"| {r['id']} | {r['kind']} | {codes} | {r['status']} |" + (f" {r['tests']} |" if with_tests else ""))
    s = summary(rows)
    out += ["", f"Structural drifts seeded: {s['structural']}; found by the gate: {s['structural_found']}",
            f"Behavioural drifts seeded: {s['behavioural']}; found by the gate: {s['behavioural_found']}",
            f"Scenarios failing the gate: {s['gate_failed']} of {s['scenarios']}"]
    if "behavioural_caught_by_tests" in s:
        out.append(f"Behavioural drifts caught by the test suite: {s['behavioural_caught_by_tests']} of "
                   f"{s['behavioural']}")
    if details:
        for r in rows:
            out += ["", f"## {r['id']}: {r['title']}", ""]
            out += [f"- {d.code} {d.item}: {d.message}" for d in r["drift"]] or ["- no drift found"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="driftcheck.report")
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--scenarios", type=Path, required=True)
    ap.add_argument("--run-tests", action="store_true")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.write(render(evaluate(args.baseline, args.scenarios, args.run_tests), args.details))
    return 0


if __name__ == "__main__":
    sys.exit(main())

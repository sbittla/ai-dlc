"""Reports for Lab 12.2 (provided).

    python -m mcpguard.report scenarios   # every scenario: findings, admitted servers, caught or not
    python -m mcpguard.report removeone   # which malicious scenarios get through with one check turned off
    python -m mcpguard.report calls       # S09 and S10: what the legitimate server returns under attack
    python -m mcpguard.report all
"""

from __future__ import annotations

import argparse
import sys

from .checks import CHECKS
from .host import call, load, run_scenario


def _codes(sessions) -> list[str]:
    return sorted({f[0] for s in sessions for f in s.findings})


def _admission(s: dict) -> bool:
    """A scenario judged at admission (not by a call)."""
    return "call" not in s


def render_scenarios() -> str:
    lines = ["| Scenario | Expected | Findings | Admitted in the last session | Result |",
             "| --- | --- | --- | --- | --- |"]
    caught = total = 0
    for s in load("scenarios.json")["scenarios"]:
        sessions = run_scenario(s)
        codes = _codes(sessions)
        ok = codes == sorted(s["expected"])
        if s["malicious"] and _admission(s):
            total += 1
            caught += bool(codes)
        result = ("call: see calls" if not _admission(s) else
                  ("caught" if codes else ("clean" if not s["malicious"] else "MISSED")))
        lines.append(f"| {s['id']} | {', '.join(s['expected']) or 'none'} | {', '.join(codes) or 'none'} | "
                     f"{', '.join(sessions[-1].admitted) or 'none'} | {result}{'' if ok else ' (unexpected)'} |")
    lines.append(f"\nMalicious scenarios caught at admission: {caught} of {total}. Benign S01: "
                 f"{'admitted in all 3 sessions' if not _codes(run_scenario(load('scenarios.json')['scenarios'][0])) else 'BLOCKED'}.")
    return "\n".join(lines)


def render_removeone() -> str:
    scenarios = [s for s in load("scenarios.json")["scenarios"] if s["malicious"] and _admission(s)]
    lines = ["| Check turned off | Malicious scenarios that get through |", "| --- | --- |"]
    for check in CHECKS:
        through = [s["id"] for s in scenarios if not _codes(run_scenario(s, disabled=frozenset({check})))]
        lines.append(f"| {check} | {', '.join(through) or 'none'} |")
    return "\n".join(lines)


def render_calls() -> str:
    lines = []
    for s in load("scenarios.json")["scenarios"]:
        if _admission(s):
            continue
        out = call(s["launches"][0]["fixture"], s["call"]["tool"], s["call"]["arguments"])
        value = out["value"]
        if value.get("ok"):
            marked = sum("[[INJECTION" in str(row) for row in value["rows"])
            lines.append(f"{s['id']}: admitted; {value['row_count']} rows returned, {marked} carrying a placeholder "
                         f"marker; result trust: {out['trust']}.")
        else:
            lines.append(f"{s['id']}: refused by Lab 3.2's policy: {value['error']}; result trust: {out['trust']}.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mcpguard.report")
    parser.add_argument("what", choices=["scenarios", "removeone", "calls", "all"])
    args = parser.parse_args(argv)
    parts = {"scenarios": render_scenarios, "removeone": render_removeone, "calls": render_calls}
    chosen = list(parts) if args.what == "all" else [args.what]
    sys.stdout.write("\n\n".join(parts[p]() for p in chosen) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

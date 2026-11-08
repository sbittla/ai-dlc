"""Write Lab 5.2's seeded drift scenarios. Deterministic: the same bytes on every run and platform.

    python scripts/generate_data.py            # writes data/scenarios/
    python scripts/generate_data.py --out DIR  # writes DIR/scenarios/ (the golden test uses this)

Input (committed, not generated): data/baseline/, a copy of Relay 4.18.0 from
labs/ch05/L5.1-spec-first-delivery/solution/relay-repo/.

Each scenario is an overlay: scenario.json (what was seeded, and what the authors
expect a drift check and the test suite to see) plus the changed files under
files/, at their paths in the repository. Applying the overlay to the baseline
gives the drifted repository.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
BASELINE = LAB / "data" / "baseline"
MODEL = "src/relay/escalation/model.py"
RULES = "src/relay/escalation/rules.py"
EVALUATE = "src/relay/escalation/evaluate.py"
SPEC = "specs/001-escalation-rules/spec.md"
CONTRACT = "specs/001-escalation-rules/contracts/escalation-rules.schema.json"
ACCEPTANCE = "tests/escalation/test_escalation_acceptance.py"

AC12 = """### ESC-AC12
Requirement: ESC-R07
Coverage: full
Criterion: Given a P2 rule with business hours 06:00 to 22:00 in Europe/Berlin and one step at 4 business hours, \
when a task's priority is set to P2 at 21:00 local time and it stays unacknowledged, then the step fires at 09:00 \
local time the next day.

## Change log
"""

EXTRA_TEST = '''

# Added by an agent while "tidying up" the test file.
def test_ESC_AC15_a_fired_step_names_its_targets():
    result = evaluate(default_rule(), TASK, p1_state(), minutes(10))
    assert result.fire[0].targets == (GUEST_INVITED.id,)
'''

SCENARIOS = [
    ("00-baseline", "No change: Relay 4.18.0 as approved", "none", {}),
    ("01-unit-renamed-in-code", "An agent renames Step.delay_minutes to delay_seconds and converts units",
     "structural", {
         MODEL: [("    delay_minutes: int  # after the task's priority was set",
                  "    delay_seconds: int  # after the task's priority was set")],
         RULES: [("        delay = step.delay_minutes\n", "        delay = step.delay_seconds // 60\n")],
         EVALUATE: [("timedelta(minutes=step.delay_minutes)", "timedelta(seconds=step.delay_seconds)")]}),
    ("02-contract-field-added", "Someone adds task_title to the Evaluation contract for a richer email",
     "structural", {
         CONTRACT: [('        "task_id": {"type": "integer", "minimum": 1},\n        "rule_id"',
                     '        "task_id": {"type": "integer", "minimum": 1},\n'
                     '        "task_title": {"type": "string"},\n        "rule_id"')]}),
    ("03-spec-bumped", "The spec moves to 1.1.0 and adds ESC-AC12; contract, code and tests stay at 1.0.0",
     "structural", {
         SPEC: [("Version: 1.0.0\n", "Version: 1.1.0\n"), ("## Change log\n", AC12)]}),
    ("04-status-added-in-code", "An agent adds a 'snoozed' status to the code only",
     "structural", {
         MODEL: [('STATUSES = ("not_applicable", "acknowledged", "active", "complete")',
                  'STATUSES = ("not_applicable", "acknowledged", "active", "complete", "snoozed")')]}),
    ("05-type-drift", "Step.delay_minutes becomes a float in the code; the contract says integer",
     "structural", {
         MODEL: [("    delay_minutes: int  # after", "    delay_minutes: float  # after")]}),
    ("06-unspecified-test", "An agent adds a test named after ESC-AC15, a criterion outside this spec",
     "structural", {ACCEPTANCE: [("__APPEND__", EXTRA_TEST)]}),
    ("07-boundary-moved", "evaluate() fires a step only after its due time, not at it (>= became >)",
     "behavioural", {EVALUATE: [("        if now >= due:\n", "        if now > due:\n")]}),
    ("08-criterion-weakened", "The delay message stops naming the range, and the test's assertion is removed",
     "behavioural", {
         RULES: [('f"Step {n} delay of {delay} minutes is outside the allowed range of "\n'
                  '                               f"{MIN_DELAY_MINUTES} to {MAX_DELAY_MINUTES} minutes."',
                  'f"Step {n} delay of {delay} minutes is not allowed."')],
         ACCEPTANCE: [('    assert "5 to 240 minutes" in str(error)\n', "")]}),
]


def apply(text: str, edits: list[tuple[str, str]], name: str) -> str:
    for old, new in edits:
        if old == "__APPEND__":
            text += new
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{name}: expected exactly one match for {old[:60]!r}")
        text = text.replace(old, new)
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=LAB / "data")
    out = ap.parse_args().out / "scenarios"
    shutil.rmtree(out, ignore_errors=True)
    for sid, title, kind, changes in SCENARIOS:
        folder = out / sid
        folder.mkdir(parents=True)
        meta = {"id": sid, "title": title, "kind": kind, "changed": sorted(changes)}
        (folder / "scenario.json").write_bytes((json.dumps(meta, indent=2) + "\n").encode("utf-8"))
        for rel, edits in changes.items():
            text = (BASELINE / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")
            target = folder / "files" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(apply(text, edits, f"{sid} {rel}").encode("utf-8"))


if __name__ == "__main__":
    main()

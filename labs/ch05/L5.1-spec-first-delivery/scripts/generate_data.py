"""Write Lab 5.1's generated data. Deterministic: the same bytes on every run and platform.

    python scripts/generate_data.py            # writes into data/
    python scripts/generate_data.py --out DIR  # writes the same files into DIR (the golden test uses this)

Inputs (committed, not generated):
  data/prd-v1.md        PRD v1.0, byte-identical to labs/ch04/L4.1-brief-to-prd/data/prd-v1.md
  data/spec-v1/         the approved spec package, identical to solution/relay-repo/specs/001-escalation-rules/

Generated:
  data/spec-scaffold/   the package with its data rules, four security constraints, every
                        coverage decision, the approval and tasks T04-T09 removed
  data/tasks-draft.md   a task list an assistant drafted from the spec, unedited
  data/incident/        what three agents built from three prompts (Chapter 5's opening incident)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
DATA = LAB / "data"
SPEC_V1 = DATA / "spec-v1"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def section(text: str, name: str) -> tuple[int, int]:
    start = text.index(f"\n## {name}\n") + 1
    nxt = text.find("\n## ", start + 1)
    return start, (nxt + 1 if nxt != -1 else len(text))


def scaffold_spec(text: str) -> str:
    text = text.replace("Status: approved\n", "Status: draft\n")
    text = re.sub(r"^(Security reviewer|Approved by|Approved on): .*\n", "", text, flags=re.M)
    s, e = section(text, "Data rules")
    classes = text[s:e].split("\n\n")[1]
    text = text[:s] + (
        "## Data rules\n\n" + classes + "\n\n"
        "Status: TO COMPLETE. One row per contract field (all 20), then the Relay fields that must never leave "
        "Relay (`Task.title`, `User.name`, `User.email`) and the triage model's suggestion. "
        "Field names are `Definition.field`, in backticks.\n\n"
        "| Field | Classification | Rule |\n| --- | --- | --- |\n\n") + text[e:]
    s, e = section(text, "Security constraints")
    body = text[s:e]
    first = body[:body.index("\n### SEC-02")]
    text = text[:s] + first + (
        "\n\nStatus: TO COMPLETE. Write SEC-02 to SEC-05, each with Source:, Checks: and Statement:. "
        "SEC-02: targets (ESC-R08, ESC-N05, ESC-N06). SEC-03: suggested priorities (ESC-N01, D3), with "
        "policy test test_SEC03. SEC-04: documents for delivery (ESC-N07), with test_SEC04. SEC-05: calls "
        "outside the process (ESC-N10), with test_SEC05.\n\n") + text[e:]
    text = re.sub(r"^Coverage: (full|partial)$", "Coverage: TO COMPLETE", text, flags=re.M)
    text = re.sub(r"^Deferred: .*\n", "", text, flags=re.M)
    text = re.sub(r"^\| 1\.0\.0 \| .*$", "| 1.0.0 | – | Draft from PRD v1.0 | – |", text, flags=re.M)
    return text


def scaffold_tasks(text: str) -> str:
    text = re.sub(r"^Reviewed by: .*\n", "", text, flags=re.M)
    head = text[:text.index("\n### T04")]
    return head + ("\n\n<!-- TO COMPLETE: tasks T04 onwards. Every criterion and security constraint in the spec "
                   "needs a task that checks it; give each task a risk, a tier and a reason. -->\n")


TASKS_DRAFT = """# Tasks — Escalation rule evaluation

Spec: ESC-SPEC-1@0.9.0
Planned by: coding assistant (draft, unedited)

### T01 — Escalation types
Checks: ESC-AC27
Depends on: –
Files: src/relay/escalation/model.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: New module.

### T02 — Rule validation and evaluation
Checks: ESC-AC02, ESC-AC06, ESC-AC08, ESC-AC09, ESC-AC10, ESC-AC11
Depends on: T01
Files: src/relay/escalation/rules.py, src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Core logic.

### T03 — Business-hours steps
Checks: ESC-AC12
Depends on: T02
Files: src/relay/escalation/hours.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: P2 rules need business hours.

### T04 — Target validation
Checks: ESC-AC13, ESC-AC14, ESC-AC26, SEC-01, SEC-02
Depends on: T02
Files: src/relay/escalation/rules.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T4
Why: Fully covered by tests, so the agent can merge when they pass.

### T05 — Suggested priorities
Checks: ESC-AC18, SEC-03
Depends on: T02
Files: src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py
Risk: high
Sensitive: yes
Untrusted input: yes
Tier: T3
Why: Uses the injection ticket TK32 as a fixture.

### T06 — SMS fallback channel
Checks: –
Depends on: T02
Files: src/relay/escalation/sms.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: INT-1 says SMS was agreed with the vendor.

### T07 — Privacy of evaluation documents
Checks: ESC-AC27, SEC-04
Depends on: T02, T11
Files: tests/escalation/test_escalation_policy.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier:
Why: Privacy guardrail.
"""

INCIDENT = [
    {
        "agent": "A",
        "prompt": "Add escalation rules to Relay so that urgent tasks escalate to the right people "
                  "when nobody responds.",
        "signature": "escalate(task, rules) -> list[Notification]",
        "rule_example": {"id": "rule-1", "priority": "P1",
                         "levels": [{"after": 600, "notify": ["shift.lead@customer.example"]},
                                    {"after": 1800, "notify": ["owner@customer.example"]}]},
        "evaluation_example": {"task": 7, "notifications": [
            {"level": 0, "to": "shift.lead@customer.example", "subject": "P1: Scanner gateway down in hall 3"}]},
    },
    {
        "agent": "B",
        "prompt": "Implement escalation rules from the PRD's P1 path: rules have steps with delays in minutes "
                  "and target users.",
        "signature": "RuleEngine.check(rule, task_state, now) -> EscalationResult",
        "rule_example": {"rule_id": "R-ROT-P1", "project": "Rotterdam",
                         "steps": [{"step": 1, "delay_minutes": 10, "user_ids": [5]},
                                   {"step": 2, "delay_minutes": 20, "user_ids": [2]}]},
        "evaluation_example": {"task_id": 7, "task_title": "Scanner gateway down in hall 3", "due_steps": [1],
                               "state": "ESCALATING"},
    },
    {
        "agent": "C",
        "prompt": "Build the escalation evaluator: P1 tasks escalate after 10 and then 20 minutes, "
                  "like our on-call policy.",
        "signature": "evaluate_escalations(now) -> None  # reads tasks and rules from the store, sends email",
        "rule_example": {"name": "P1 default", "trigger": "priority_or_suggestion", "threshold_minutes": [10, 20],
                         "escalate_to": "workspace_owner"},
        "evaluation_example": {"escalated": [{"task_id": 7, "minutes_waiting": 10, "recipient_role": "Owner"}]},
    },
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DATA)
    out = ap.parse_args().out
    for sub in ("spec-scaffold", "incident"):
        shutil.rmtree(out / sub, ignore_errors=True)
    spec = (SPEC_V1 / "spec.md").read_bytes().decode("utf-8")
    tasks = (SPEC_V1 / "tasks.md").read_bytes().decode("utf-8")
    write(out / "spec-scaffold" / "spec.md", scaffold_spec(spec))
    write(out / "spec-scaffold" / "tasks.md", scaffold_tasks(tasks))
    contract = SPEC_V1 / "contracts" / "escalation-rules.schema.json"
    write(out / "spec-scaffold" / "contracts" / contract.name, contract.read_bytes().decode("utf-8"))
    write(out / "tasks-draft.md", TASKS_DRAFT)
    for agent in INCIDENT:
        write(out / "incident" / f"agent-{agent['agent'].lower()}.json", json.dumps(agent, indent=2) + "\n")


if __name__ == "__main__":
    main()

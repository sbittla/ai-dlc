"""Write every GENERATED file in data/ (deterministic; byte-identical on every platform).

    python scripts/generate_data.py

Generated from the reference solution's Relay 4.20.0 by exact text substitution:

- data/variants/<id>/...      nine seeded bugs, each a copy of one or two Relay files with one fault
- data/variants/manifest.json what each bug is, and which test file must catch it
- data/agent-pr/src/...       the opening incident's agent code: engine.py, delivery.py and hours.py
- data/relay-4.19.0-manifest.json  SHA-256 of every canonical 4.19.0 file, to prove what 4.20.0 changed

Not generated (lab input): data/prd-v1.1.md, data/agent-pr/tests/ and data/agent-pr/README.md.
Every substitution must match exactly once, so a change to the reference that
moves a seeded line fails here instead of producing a variant that is not a bug.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
REF = LAB / "solution" / "relay-repo"
DATA = LAB / "data"
BASELINE = LAB.parent.parent / "relay-baselines" / "4.19.0" / "relay-repo"
HOURS = "src/relay/escalation/hours.py"
DELIVERY = "src/relay/escalation/delivery.py"
ENGINE = "src/relay/escalation/engine.py"

WEBHOOK_BLOCK = '''        if config.webhook is not None:
            body = event_body(escalation_event(decision, rule, project, task.id, link, started, now))
            headers = {"Content-Type": "application/json", "X-Relay-Event": "task.escalated",
                       SIGNATURE_HEADER: sign(body, config.webhook.secret)}
            store.add_outbox(f"webhook:{task.id}:{rule.rule_id}:{decision.step}", now, "webhook", "task.escalated",
                             config.webhook.url, headers, body.decode("utf-8"))
            result.events += 1
'''

VARIANTS = [
    ("H1-utc-windows", "hours", "Windows are read in UTC, not the rule's zone. ESC-AC12's own example still passes.",
     {HOURS: [("    return to_utc(hours.time_zone, opens), to_utc(hours.time_zone, closes)\n",
               "    return opens.replace(tzinfo=UTC), closes.replace(tzinfo=UTC)\n"),
              ("    day = to_local(hours.time_zone, start).date()\n", "    day = start.date()\n")]}),
    ("H2-close-rolls-over", "hours", "A delay ending exactly at the close is due at the next opening instead.",
     {HOURS: [("            if begin <= closes and remaining <= closes - begin:\n",
               "            if begin < closes and remaining < closes - begin:\n")]}),
    ("H3-weekends-count", "hours", "Every day is a business day, whatever the rule lists (D10 ignored).",
     {HOURS: [("    if day.isoweekday() not in hours.days:\n        return None\n", "")]}),
    ("H4-no-daylight-saving", "hours", "Each zone keeps its standard offset all year (D11 ignored).",
     {HOURS: [("        if start <= instant < end:\n            return zone.daylight\n",
               "        if start <= instant < end:\n            return zone.standard\n")]}),
    ("H5-counts-before-opening", "hours", "Minutes before the window opens are counted as business minutes.",
     {HOURS: [("            begin = max(start, opens)\n", "            begin = start if start < closes else opens\n")]}),
    ("D1-title-in-subject", "delivery", "The email subject carries the first 22 characters of the task's title.",
     {ENGINE: [("            message = escalation_email(decision, target, rule, project, task.id, link, started, now)\n",
                "            message = escalation_email(decision, target, rule, project, task.id, link, started, now,\n"
                "                                       task.title)\n")],
      DELIVERY: [("                     link: str, delay_started_at: datetime, fired_at: datetime) -> EmailMessage:\n",
                  "                     link: str, delay_started_at: datetime, fired_at: datetime,\n"
                  "                     title: str = \"\") -> EmailMessage:\n"),
                 ("    subject = f\"[Relay] {rule.priority} escalation in {project.name}: step {decision.step} of "
                  "{rule_label(rule)}\"\n",
                  "    subject = f\"[Relay] {rule.priority} escalation: {title[:22]}...\"\n")]}),
    ("D2-signs-other-bytes", "delivery", "The signature is computed over re-serialised JSON, not the bytes sent.",
     {DELIVERY: [("    return \"sha256=\" + hmac.new(secret, body, hashlib.sha256).hexdigest()\n",
                  "    canonical = json.dumps(json.loads(body), sort_keys=True).encode(\"utf-8\")\n"
                  "    return \"sha256=\" + hmac.new(secret, canonical, hashlib.sha256).hexdigest()\n")]}),
    ("D3-event-per-target", "delivery", "One task.escalated event is sent per target instead of one per step.",
     {ENGINE: [(WEBHOOK_BLOCK, WEBHOOK_BLOCK.replace("        if config.webhook is not None:\n",
                                                     "        for target in decision.targets if config.webhook else ():\n")
                .replace("{decision.step}\", now", "{decision.step}:{target}\", now"))]}),
    ("D4-project-link", "delivery", "The webhook event links to the project, not the task.",
     {DELIVERY: [("    return WebhookEvent(\"task.escalated\", SPEC_VERSION, task_id, link, rule.priority,",
                  "    return WebhookEvent(\"task.escalated\", SPEC_VERSION, task_id, link.rsplit(\"/tasks/\", 1)[0], "
                  "rule.priority,")]}),
]

AGENT = {
    ENGINE: [("            message = escalation_email(decision, target, rule, project, task.id, link, started, now)\n",
              "            message = escalation_email(decision, target, rule, project, task, link, started, now)\n"),
             ("            body = event_body(escalation_event(decision, rule, project, task.id, link, started, now))\n",
              "            body = event_body(escalation_event(decision, rule, project, task, link, started, now))\n")],
    DELIVERY: [("from ..models import Project\n", "from ..models import Project, Task\n"),
               ("def escalation_email(decision: StepDecision, to_user: int, rule: Rule, project: Project, task_id: int,\n",
                "def escalation_email(decision: StepDecision, to_user: int, rule: Rule, project: Project, task: Task,\n"),
               ("    subject = f\"[Relay] {rule.priority} escalation in {project.name}: step {decision.step} of "
                "{rule_label(rule)}\"\n",
                "    subject = f\"[Relay] {rule.priority} escalation: {_short(task.title)}\"\n"),
               ("        f\"Relay task {task_id}\",\n", "        f\"Relay task {task.id}\",\n"),
               ("def escalation_event(decision: StepDecision, rule: Rule, project: Project, task_id: int, link: str,\n",
                "def escalation_event(decision: StepDecision, rule: Rule, project: Project, task: Task, link: str,\n"),
               ("    return WebhookEvent(\"task.escalated\", SPEC_VERSION, task_id, link,",
                "    return WebhookEvent(\"task.escalated\", SPEC_VERSION, task.id, link,"),
               ("    return json.dumps(to_document(event), sort_keys=True, separators=(\",\", \":\"), "
                "ensure_ascii=False).encode(\"utf-8\")\n",
                "    return json.dumps(to_document(event), separators=(\",\", \":\")).encode(\"utf-8\")\n"),
               ("    return \"sha256=\" + hmac.new(secret, body, hashlib.sha256).hexdigest()\n",
                "    canonical = json.dumps(json.loads(body), sort_keys=True).encode(\"utf-8\")  # stable key order\n"
                "    return \"sha256=\" + hmac.new(secret, canonical, hashlib.sha256).hexdigest()\n"),
               ("def summary_email(", "def _short(title: str) -> str:\n"
                "    \"\"\"Titles are long; 22 characters is enough to recognise the task in an inbox.\"\"\"\n"
                "    return title if len(title) <= 22 else title[:22] + \"...\"\n\n\n"
                "def summary_email(")],
    HOURS: VARIANTS[0][3][HOURS],
}


def patched(rel: str, substitutions: list[tuple[str, str]]) -> str:
    text = (REF / rel).read_text(encoding="utf-8")
    for old, new in substitutions:
        if text.count(old) != 1:
            raise SystemExit(f"{rel}: expected exactly one match for {old[:60]!r}, found {text.count(old)}")
        text = text.replace(old, new)
    return text


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> None:
    manifest = []
    for vid, group, what, files in VARIANTS:
        for rel, subs in files.items():
            write(DATA / "variants" / vid / rel, patched(rel, subs))
        manifest.append({"id": vid, "group": group, "description": what, "files": sorted(files)})
    write(DATA / "variants" / "manifest.json", json.dumps({"variants": manifest}, indent=2) + "\n")
    for rel, subs in AGENT.items():
        write(DATA / "agent-pr" / rel, patched(rel, subs))
    files = sorted(p for p in BASELINE.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                   and ".pytest_cache" not in p.parts)
    if not files:
        raise SystemExit(f"canonical 4.19.0 not found at {BASELINE}: refusing to write an empty manifest")
    write(DATA / "relay-4.19.0-manifest.json", json.dumps(
        {"version": "4.19.0", "source": "labs/relay-baselines/4.19.0/relay-repo",
         "sha256": {p.relative_to(BASELINE).as_posix(): digest(p) for p in files}}, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(manifest)} variants, the agent's code ({len(AGENT)} files) and the 4.19.0 manifest "
          f"({len(files)} files)")


if __name__ == "__main__":
    main()

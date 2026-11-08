"""Write Lab 4.2's data: a labelled set of requirement statements with seeded
defects, and two detector lexicons.

    python scripts/generate_data.py            # rewrite data/
    python scripts/generate_data.py --out DIR  # write the same files somewhere else

data/statements.jsonl  96 statements in 24 sets of 4 (12 dev sets, 12 held-out sets)
data/lexicon-v1.json   the baseline detector lexicon, carried over from Lab 4.1
data/lexicon-v2.json   v1 plus the words added after reading the detector's misses on dev

The statements are synthetic. The authors wrote them and seeded the defects;
the labels are the defects they seeded, reviewed once by a second reader.
The held-out sets were written later, by a different author, who did not see
the dev sets or the detector. They therefore use some different vague words
and phrasings: the gap between the splits was built into this data, as the
gap between keyword and paraphrased questions was in Lab 2.2.

Defect types (a statement may have more than one, or none):
    ambiguity      a word or phrase two careful readers could interpret differently
    untestable     no observation could show it false: a weak modal ("should", "is expected to"),
                   or a quality of the system's behaviour (speed, availability, reliability,
                   scale) with no threshold. A vague noun phrase ("the relevant people") is
                   ambiguity only; a vague quality ("quickly", "regularly") is both
    contradiction  cannot be true at the same time as another statement in its set
    missing_actor  does not name who performs the action or who receives its result
Output is byte-identical on every platform (UTF-8, LF line endings).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent

A, U, C, M = "ambiguity", "untestable", "contradiction", "missing_actor"

# (set id, topic, [(text, defects, conflicts_with_index_in_set or None), ...])
DEV = [
    ("D01", "escalation timing", [
        ("When a P1 task stays unacknowledged for 10 minutes, Relay must notify the first step's targets.", [C], 1),
        ("When a P1 task stays unacknowledged for 15 minutes, Relay must notify the first step's targets.", [C], 0),
        ("Relay must notify the relevant people within 20 minutes when a P1 task is still unacknowledged.", [A], None),
        ("An Admin can set each step's delay to a whole number of minutes from 5 to 240.", [], None),
    ]),
    ("D02", "rule editing", [
        ("Only an Owner or an Admin can change an escalation rule.", [C], 1),
        ("A Member can change the escalation rules of any project they belong to.", [C], 0),
        ("The rule editor should show a preview of each step before saving.", [U], None),
        ("A warning is shown within 1 minute when a rule has no valid target.", [M], None),
    ]),
    ("D03", "notifications", [
        ("Relay must email each target within 60 seconds of a step firing.", [], None),
        ("Escalation emails must contain the appropriate task details and the task's link.", [A], None),
        ("A summary email is sent at the end of each hour.", [M], None),
        ("Relay must send at most 20 escalation emails per target per hour.", [], None),
    ]),
    ("D04", "webhooks", [
        ("Relay must sign every task.escalated webhook event with HMAC-SHA256 in the X-Relay-Signature header.", [], None),
        ("Webhook delivery must be highly available.", [U], None),
        ("Relay must retry a failed webhook delivery 8 times, with the last attempt 6 hours after the first.", [], None),
        ("Webhook payloads must stay under 256 KB and include large attachments by reference when needed.", [A], None),
    ]),
    ("D05", "acknowledgement", [
        ("An assignee can acknowledge a task from the task page or from the escalation email.", [], None),
        ("Acknowledgement should happen soon after the first notification.", [A, U], None),
        ("A comment added by a service token must not count as an acknowledgement.", [], None),
        ("The acknowledgement time is displayed in UTC.", [M], None),
    ]),
    ("D06", "business hours", [
        ("A P2 rule counts only its own business hours, from a daily start time to an end time in one time zone.", [], None),
        ("A new P2 rule must start with one step at 4 business hours.", [C], 2),
        ("A new P2 rule must start with one step at 8 business hours.", [C], 1),
        ("Business hours must be flexible enough for every warehouse, with up to 7 schedules per rule.", [A], None),
    ]),
    ("D07", "suggested priority", [
        ("A priority suggested by the triage model must not start an escalation.", [], None),
        ("The task page must show the model's confidence as a percentage next to its suggestion.", [], None),
        ("Support agents should be able to override a suggested priority.", [U], None),
        ("Overrides are logged as appropriate.", [A, M], None),
    ]),
    ("D08", "exports", [
        ("An Admin can export up to 50,000 tasks as CSV or JSON.", [], None),
        ("Relay must keep each export file for 7 days and then delete it.", [], None),
        ("Exports must scale to any workspace size.", [U], None),
        ("Export files are emailed when they are ready.", [M], None),
    ]),
    ("D09", "notification settings", [
        ("A user can turn off each notification type in Profile settings.", [], None),
        ("Relay must suppress email to an address for 30 days after it is marked as spam.", [], None),
        ("The settings page must remind users several times that escalation emails ignore notification settings.", [A], None),
        ("Admins can set default notification preferences for new members.", [], None),
    ]),
    ("D10", "SSO sessions", [
        ("On the Business plan, an Admin can require SSO with SAML 2.0 or OpenID Connect.", [], None),
        ("SSO sessions must last 12 hours by default.", [C], 2),
        ("SSO sessions must last 8 hours by default.", [C], 1),
        ("Session expiry should be handled gracefully.", [U, M], None),
    ]),
    ("D11", "API limits", [
        ("Relay must answer requests above 600 per minute per workspace token with HTTP 429 and a Retry-After header.", [], None),
        ("Bulk endpoints must count as 10 requests each.", [], None),
        ("The API must handle bursts reliably.", [U], None),
        ("Repeated violations for more than 15 minutes trigger an alert.", [M], None),
    ]),
    ("D12", "roles", [
        ("Only the Owner can see the Billing tab.", [], None),
        ("A Guest can see only the projects they are invited to.", [], None),
        ("Guests must not see the member directory, except when it is relevant to their project.", [A], None),
        ("A workspace must have exactly one Owner, and ownership can be transferred quickly.", [A, U], None),
    ]),
]

HELD_OUT = [
    ("H01", "escalation steps", [
        ("Each rule must have at least 1 step and each step at least 1 target.", [], None),
        ("Relay must cancel the remaining steps within 30 seconds of an acknowledgement.", [], None),
        ("A step that has already fired must not fire again for the same task.", [C], 3),
        ("Relay must repeat the last step every 10 minutes until the task is acknowledged.", [C], 2),
    ]),
    ("H02", "targets", [
        ("A Guest can be a target only in projects they are invited to.", [], None),
        ("Targets outside the workspace must never be accepted.", [M], None),
        ("Relay must refuse a rule whose targets include a user who cannot view the project.", [], None),
        ("Rules must support a reasonable number of targets.", [A, U], None),
    ]),
    ("H03", "email content", [
        ("Escalation emails must not contain the task's title or description.", [], None),
        ("Escalation emails must carry the task's link, its priority and the rule's name.", [], None),
        ("Delivery failures are reported to the workspace.", [M], None),
        ("Email delivery is expected to succeed in most cases.", [U], None),
    ]),
    ("H04", "flood limits", [
        ("Relay must send at most 20 escalation emails per target per hour.", [C], 1),
        ("Relay must send at most 50 escalation emails per target per hour.", [C], 0),
        ("Excess escalations must be listed in one summary email at the end of the hour.", [M], None),
        ("The flood limit should be adjustable by Admins.", [U], None),
    ]),
    ("H05", "audit", [
        ("Relay must write an audit log entry for every rule change within 5 seconds.", [], None),
        ("Relay must keep audit entries for 400 days on the Business plan.", [C], 2),
        ("Relay must keep audit entries for 90 days on the Business plan.", [C], 1),
        ("The audit view must be intuitive for Admins.", [A, U], None),
    ]),
    ("H06", "accessibility", [
        ("The rule editor must meet WCAG 2.2 level AA.", [], None),
        ("Every rule action must be possible with the keyboard alone.", [], None),
        ("Screen readers must announce each field's label.", [], None),
        ("Error messages must be adequate for screen-reader users.", [A, U], None),
    ]),
    ("H07", "operability", [
        ("95% of steps must fire within 60 seconds of their due time, measured weekly.", [], None),
        ("If the evaluator stops for 5 minutes, Relay must page the platform on-call engineer.", [], None),
        ("The evaluator must recover robustly from crashes.", [U], None),
        ("Stalls are surfaced on a dashboard.", [M], None),
    ]),
    ("H08", "cost", [
        ("Version 1 must add $0 per notification beyond Relay's existing email and webhook delivery.", [], None),
        ("Escalation evaluation must add at most 5% to the worker's CPU time.", [], None),
        ("Costs must remain sufficient for the pilot's budget.", [A, U], None),
        ("SMS may be added later if a customer pays for it.", [U], None),
    ]),
    ("H09", "suggested priority", [
        ("The task must show 'Suggested: P1 (91%)' when the model suggests P1 with 91% confidence.", [], None),
        ("A person must confirm a suggested P1 before any step starts.", [C], 2),
        ("A suggested P1 with confidence of 95% or more must start the first step without confirmation.", [C], 1),
        ("Overrides are recorded with the time.", [M], None),
    ]),
    ("H10", "retention", [
        ("Relay must keep deleted rules in the trash for 30 days.", [], None),
        ("Any Admin can restore a deleted rule within 30 days.", [], None),
        ("Rules deleted after that are purged shortly.", [A, U, M], None),
        ("Relay must keep backups of rules for a significant time.", [A, U], None),
    ]),
    ("H11", "exports", [
        ("An Admin can start at most 5 concurrent export jobs per workspace.", [], None),
        ("Relay must include each task's escalation history in JSON exports.", [], None),
        ("Exports started during a deploy must be retried automatically where possible.", [U, M], None),
        ("Export links must expire regularly.", [A, U], None),
    ]),
    ("H12", "webhook payloads", [
        ("Relay must emit one task.escalated event per fired step.", [], None),
        ("Receivers must verify the X-Relay-Signature header with the webhook secret.", [], None),
        ("Payloads larger than 256 KB must be truncated and flagged.", [M], None),
        ("Relay must emit the event within 60 seconds of the step firing.", [], None),
    ]),
]

LEXICON_V1 = {
    "lexicon_version": "detector-lexicon-v1",
    "note": "Carried over from Lab 4.1's lexicon, plus a first list of quality words and actor terms.",
    "vague_terms": [
        "adequate", "and/or", "appropriate", "as needed", "easy", "efficient", "etc.", "fast", "flexible",
        "intuitive", "minimal", "quickly", "reasonable", "relevant", "right people", "robust", "seamless",
        "secure", "simple", "timely", "urgent", "user-friendly",
    ],
    "weak_modals": ["should", "may", "might", "could", "ideally", "where possible", "if possible", "try to"],
    "quality_terms": ["available", "reliable", "reliably", "secure"],
    "measurable_patterns": [
        r"\$\d",
        r"\b\d+(\.\d+)?\s*(%|(ms|milliseconds?|seconds?|minutes?|hours?|business hours|days?|KB|MB)\b)",
        r"\b(at most|at least|no more than|up to) \d+",
        r"\bWCAG \d\.\d\b",
        r"\bmust not\b",
    ],
    "actor_terms": [
        "Relay", "Owner", "Owners", "Admin", "Admins", "Member", "Members", "Guest", "Guests", "user", "users",
        "assignee", "target", "targets", "person", "agent", "agents", "engineer", "manager", "customer",
        "receivers", "reviewer", "caller",
    ],
    "passive_pattern": r"(?i)\b(is|are|be|been|being|was|were)\s+(\w+ed|sent|shown|kept|done|made|given|taken|seen|written|run|set|built|held)\b",
    "contradiction": {"min_overlap": 0.5, "min_overlap_polarity": 0.6},
}

LEXICON_V2 = dict(LEXICON_V1)
LEXICON_V2.update({
    "lexicon_version": "detector-lexicon-v2",
    "note": "v1 plus the words found by reading the detector's misses on the dev split. Tuned on dev: report it on held-out.",
    "vague_terms": sorted(LEXICON_V1["vague_terms"] + ["large", "several", "soon", "when needed"]),
    "quality_terms": LEXICON_V1["quality_terms"] + ["scale"],
})


def rows() -> list[dict]:
    out, n = [], 0
    for split, sets in (("dev", DEV), ("heldout", HELD_OUT)):
        for set_id, topic, items in sets:
            assert len(items) == 4, set_id
            ids = [f"S{n + i + 1:03d}" for i in range(4)]
            for i, (text, defects, other) in enumerate(items):
                assert (C in defects) == (other is not None), (set_id, i)
                out.append({"id": ids[i], "set": set_id, "split": split, "topic": topic, "text": text,
                            "defects": sorted(defects), "conflicts_with": ids[other] if other is not None else None})
            n += 4
    return out


def lf(text: str) -> bytes:
    return text.replace("\r\n", "\n").encode("utf-8")


def files() -> dict[str, bytes]:
    return {
        "statements.jsonl": lf("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows())),
        "lexicon-v1.json": lf(json.dumps(LEXICON_V1, indent=2) + "\n"),
        "lexicon-v2.json": lf(json.dumps(LEXICON_V2, indent=2) + "\n"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=LAB / "data")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files().items()):
        (args.out / name).write_bytes(content)
    print(f"wrote {len(files())} files to {args.out}")


if __name__ == "__main__":
    main()

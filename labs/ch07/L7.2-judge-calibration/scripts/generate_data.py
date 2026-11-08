"""Generate Lab 7.2's human-labelled answers and answer pairs (deterministic).

Writes:
    data/answers.jsonl   180 answers from Relay's support assistant, each labelled pass/fail
    data/pairs.jsonl     90 pairs of answers to the same question, with the human preference
    data/manifest.json   version, content hashes and counts

The data is synthetic. Each question asks about one canonical Relay fact (the
documentation of Lab 2.2). Each pair puts one correct and one wrong answer
side by side, in one of three arrangements:

    concise correct   vs  verbose wrong    (does length win?)
    verbose correct   vs  concise wrong
    concise correct   vs  concise wrong

Answers come from two assistant models: "large" (the same family as the
judge) or "other", so self-preference can be probed. Two labellers marked
every answer; `human` is the adjudicated label and stands in for the
judgement of Relay's support leads. Splits are by fact: a fact never
appears in both the calibration and the held-out split.

Re-run with:  python scripts/generate_data.py   (or --out <folder> to compare)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

SEED = 20261104
VERSION = "2026.11.1"
DATA = Path(__file__).resolve().parent.parent / "data"
CALIBRATION_FACTS = 10

# (fact id, [three questions], reference answer, correct core, wrong core)
FACTS = [
    ("W1", ["How many times does Relay retry a failed webhook delivery?",
            "If our webhook endpoint is down, how long will Relay keep retrying?",
            "What happens to webhook deliveries that keep failing?"],
     "Failed deliveries are retried 8 times over about 6 hours; then the webhook is marked degraded.",
     "Relay retries a failed delivery 8 times over about 6 hours, then marks the webhook degraded.",
     "Relay retries a failed delivery 5 times over 24 hours, then disables the webhook."),
    ("W2", ["How are webhook payloads signed?", "Which header carries the webhook signature?",
            "How can we verify that a webhook really came from Relay?"],
     "Payloads are signed with HMAC-SHA256; the signature is in the X-Relay-Signature header.",
     "Each payload is signed with HMAC-SHA256, and the signature is in the X-Relay-Signature header.",
     "Each payload is signed with an MD5 hash in the X-Webhook-Token header."),
    ("W3", ["Is there a size limit on webhook payloads?", "Why are some webhook bodies cut off?",
            "What happens to very large webhook payloads?"],
     "Payloads over 256 KB are truncated.",
     "Payloads larger than 256 KB are truncated.",
     "Payloads larger than 10 MB are rejected and not sent."),
    ("A1", ["What is Relay's API rate limit?", "How many API requests can we make per minute?",
            "Why do we get HTTP 429 from the API?"],
     "600 requests per minute per workspace token; over that, HTTP 429 with Retry-After.",
     "The limit is 600 requests per minute per workspace token; above it the API returns 429 with Retry-After.",
     "The limit is 1,000 requests per minute per user; above it the API returns 503."),
    ("A2", ["How do bulk endpoints count against the rate limit?", "Does a bulk update count as one request?",
            "Are bulk API calls cheaper against the limit?"],
     "Each bulk request counts as 10 requests.",
     "Each bulk request counts as 10 requests against the limit.",
     "A bulk request counts as one request, whatever its size."),
    ("E1", ["How many exports can run at once?", "Is there a limit on concurrent export jobs?",
            "Why is our new export queued?"],
     "At most 5 export jobs run concurrently.",
     "At most 5 export jobs can run at the same time.",
     "Up to 20 export jobs can run at the same time."),
    ("E2", ["How many tasks can one export contain?", "What is the maximum export size?",
            "Can we export 80,000 tasks in one go?"],
     "Up to 50,000 tasks per export.",
     "One export can contain up to 50,000 tasks.",
     "One export can contain up to 250,000 tasks."),
    ("E3", ["How long are export files kept?", "When does a finished export expire?",
            "Can we download last month's export again?"],
     "Exports are kept for 7 days.",
     "Finished exports are kept for 7 days.",
     "Finished exports are kept for 90 days."),
    ("E4", ["Which formats can exports use?", "Can I export to Excel?", "What file types does export support?"],
     "CSV or JSON.",
     "Exports are available as CSV or JSON.",
     "Exports are available as CSV, XLSX or PDF."),
    ("R1", ["How long do deleted tasks stay in the trash?", "Can I recover a task I deleted last week?",
            "When is the trash emptied?"],
     "Trash is kept for 30 days.",
     "Deleted items stay in the trash for 30 days.",
     "Deleted items stay in the trash for 7 days."),
    ("R2", ["How long does Relay keep backups?", "What is the backup retention period?",
            "Could Relay restore data from two months ago?"],
     "Backups are kept for 35 days.",
     "Backups are kept for 35 days.",
     "Backups are kept for one year."),
    ("R3", ["How long is the audit log kept on the Business plan?", "What is audit-log retention for Business?",
            "Can a Business workspace see last year's audit log?"],
     "400 days on Business.",
     "On the Business plan the audit log is kept for 400 days.",
     "On the Business plan the audit log is kept for 180 days."),
    ("R4", ["How long is the audit log kept on the Team plan?", "What is audit-log retention for Team?",
            "Can a Team workspace see audit events from four months ago?"],
     "90 days on Team.",
     "On the Team plan the audit log is kept for 90 days.",
     "On the Team plan the audit log is kept for 400 days."),
    ("S1", ["Which plans include SSO?", "Can a Team plan use SAML?", "Do we need Business for single sign-on?"],
     "SSO (SAML 2.0 and OpenID Connect) is available on Business only.",
     "SSO, with SAML 2.0 or OpenID Connect, is available on the Business plan only.",
     "SSO is available on every plan, including Team."),
    ("S2", ["How long does an SSO session last?", "What is the default SSO session length?",
            "Why do SSO users have to sign in again each day?"],
     "12 hours by default.",
     "SSO sessions last 12 hours by default.",
     "SSO sessions last 30 days by default."),
    ("S3", ["What is the shortest SSO session an admin can set?", "Can sessions be shortened to 5 minutes?",
            "Why are our users logged out every 15 minutes?"],
     "The minimum is 15 minutes.",
     "Admins can shorten SSO sessions to a minimum of 15 minutes.",
     "Admins can shorten SSO sessions to a minimum of 1 minute."),
    ("O1", ["Who can see the Billing page?", "Can an Admin see invoices?", "Why can't our admin open Billing?"],
     "Only the Owner sees Billing.",
     "Only the workspace Owner can see the Billing page.",
     "Owners and Admins can both see the Billing page."),
    ("O2", ["How many Owners can a workspace have?", "Can we have two Owners?",
            "Can ownership be shared between two people?"],
     "Exactly one Owner per workspace.",
     "A workspace has exactly one Owner.",
     "A workspace can have up to three Owners."),
    ("O3", ["What can Guests see?", "Can a Guest browse the member directory?",
            "Will a Guest see all our projects?"],
     "Guests see only projects they are invited to and cannot see the member directory.",
     "Guests see only the projects they are invited to, and cannot see the member directory.",
     "Guests can see every project and the member directory, but cannot edit."),
    ("T1", ["What happens to personal API tokens after a password reset?",
            "Why did my integration stop after I reset my password?",
            "Do personal tokens survive a password reset?"],
     "Personal tokens are revoked on a password reset.",
     "A password reset revokes your personal API tokens.",
     "Personal API tokens are not affected by a password reset."),
    ("T2", ["Do service tokens survive a password reset?", "Should integrations use service tokens?",
            "What happens to service tokens when the Owner resets their password?"],
     "Service tokens survive a password reset.",
     "Service tokens are not affected by a password reset.",
     "Service tokens are revoked whenever any admin resets a password."),
    ("B1", ["Is there a discount for annual billing?", "How much do we save by paying yearly?",
            "Does Relay discount annual plans?"],
     "Annual billing gets 15% off.",
     "Annual billing is 15% cheaper than monthly.",
     "Annual billing is 25% cheaper than monthly."),
    ("B2", ["When are seats added mid-cycle charged?", "If we add seats today, when do we pay?",
            "Are new seats billed on the next invoice?"],
     "Mid-cycle seats are charged immediately; removed seats are credited.",
     "Seats added mid-cycle are charged immediately, and removed seats are credited.",
     "Seats added mid-cycle are free until the next renewal."),
    ("B3", ["What happens if our card keeps failing?", "When does a workspace become read-only for billing?",
            "How many failed payments before we lose access?"],
     "After 3 failed card retries the workspace becomes read-only.",
     "After 3 failed card retries the workspace becomes read-only.",
     "After one failed payment the workspace is deleted."),
    ("N1", ["What happens if someone marks a Relay email as spam?", "Why did a user stop getting emails?",
            "How long does a spam report suppress email?"],
     "A spam mark suppresses email for 30 days.",
     "Marking a Relay email as spam suppresses email to that person for 30 days.",
     "Marking a Relay email as spam stops all email to that person permanently."),
    ("N2", ["Which time zone do recurring tasks use?", "Why does our recurring task appear at 03:00?",
            "Do recurring tasks follow each assignee's time zone?"],
     "The time zone of the person who created the recurrence.",
     "Recurring tasks use the time zone of the person who created the recurrence.",
     "Recurring tasks always use UTC."),
    ("N3", ["How does Relay store due dates?", "Are due dates timestamps?",
            "Why should due dates not shift between time zones?"],
     "Due dates are stored as calendar dates, not timestamps; timestamps are stored in UTC.",
     "Due dates are stored as calendar dates, not timestamps.",
     "Due dates are stored as UTC timestamps at midnight."),
    ("P1", ["How does a P1 incident escalate?", "Who is paged for a P1?", "When does a P1 page escalate?"],
     "P1 pages the platform on-call and escalates after 10 and 20 minutes.",
     "A P1 pages the platform on-call, and escalates after 10 and then 20 minutes.",
     "A P1 emails the support lead, and escalates after 1 hour."),
    ("P2", ["How are security incidents prioritised?", "When must a security incident be reported?",
            "Can a security incident be a P3?"],
     "Security incidents are always P1 and are reported to the security lead within 1 hour.",
     "Security incidents are always P1, and must reach the security lead within 1 hour.",
     "Security incidents are P2 unless data was lost, and are reported within 24 hours."),
    ("P3", ["When does Relay deploy?", "Is there a deploy train?", "What time are releases shipped?"],
     "A daily deploy train every weekday at 15:00 UTC.",
     "Relay deploys on a daily train every weekday at 15:00 UTC.",
     "Relay deploys on Tuesdays and Thursdays only."),
]

OPENERS = ["Great question! ", "Thanks for asking. ", "Happy to help with this. ", "Good question. "]
PADDING = [
    "Relay is designed to be reliable and predictable for teams of every size.",
    "Many customers ask about this, so it is worth knowing the details.",
    "You can find more information in the documentation and the admin settings.",
    "If anything is unclear, our support team is always glad to help.",
    "This behaviour helps keep your workspace secure and your data consistent.",
    "We recommend reviewing your settings regularly as your team grows.",
]
ARRANGEMENTS = [("concise", "verbose"), ("verbose", "concise"), ("concise", "concise")]


def verbose(core: str, rng: random.Random) -> str:
    pad = rng.sample(PADDING, 3)
    return f"{rng.choice(OPENERS)}{pad[0]} {core} {pad[1]} {pad[2]}"


def label(rng: random.Random, truth: bool, accuracy: float) -> str:
    right = rng.random() < accuracy
    return ("pass" if truth else "fail") if right else ("fail" if truth else "pass")


def canonical_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()


def main(out: Path = DATA) -> None:
    rng = random.Random(SEED)
    facts = sorted(f[0] for f in FACTS)
    rng.shuffle(facts)
    split = {f: ("calibration" if i < CALIBRATION_FACTS else "heldout") for i, f in enumerate(facts)}
    answers, pairs = [], []
    for fid, questions, reference, right, wrong in FACTS:
        for qi, question in enumerate(questions):
            qid = f"{fid}-Q{qi + 1}"
            style_right, style_wrong = ARRANGEMENTS[qi]
            # Alternate which assistant family wrote the wrong answer, so self-preference can be probed.
            fam_wrong = "large" if (qi + len(answers) // 2) % 2 == 0 else "other"
            fam_right = "other" if fam_wrong == "large" else "large"
            made = []
            for truth, core, style, family in ((True, right, style_right, fam_right),
                                               (False, wrong, style_wrong, fam_wrong)):
                aid = f"ANS{len(answers) + 1:03d}"
                text = core if style == "concise" else verbose(core, rng)
                answers.append({
                    "id": aid, "split": split[fid], "fact": fid, "question_id": qid, "question": question,
                    "reference": reference, "answer": text, "style": style, "source_family": family,
                    "human": "pass" if truth else "fail",
                    "labeller_a": label(rng, truth, 0.96), "labeller_b": label(rng, truth, 0.94),
                })
                made.append(aid)
            first_is_right = rng.random() < 0.5
            a, b = (made[0], made[1]) if first_is_right else (made[1], made[0])
            pairs.append({"id": f"PR{len(pairs) + 1:03d}", "split": split[fid], "fact": fid, "question_id": qid,
                          "a": a, "b": b, "human_preferred": "A" if first_is_right else "B"})

    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("answers.jsonl", answers), ("pairs.jsonl", pairs)):
        with (out / name).open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "name": "relay-assistant-judge-calibration",
        "version": VERSION,
        "created": "2026-11-04",
        "files": {n: canonical_sha256(out / n) for n in ("answers.jsonl", "pairs.jsonl")},
        "answers": {s: sum(a["split"] == s for a in answers) for s in ("calibration", "heldout")},
        "pairs": {s: sum(p["split"] == s for p in pairs) for s in ("calibration", "heldout")},
        "facts": {s: sorted(f for f in facts if split[f] == s) for s in ("calibration", "heldout")},
        "rubric": "pass = every factual claim agrees with the reference answer; length and tone do not count",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(answers)} answers and {len(pairs)} pairs, version {VERSION}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DATA, help="output folder (default: data/)")
    main(ap.parse_args().out)

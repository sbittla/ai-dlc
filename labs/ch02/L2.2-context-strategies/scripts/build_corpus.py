"""Write Relay's documentation corpus and labelled questions for Lab 2.2.

The corpus is small on purpose (12 short documents) so you can read all of it
and check every retrieval result by eye. Each question has one source
document and an answer phrase that appears in that document verbatim.

    python scripts/build_corpus.py
"""

from __future__ import annotations

import json
from pathlib import Path

DOCS = {
    "api-rate-limits.md": """# API Rate Limits

Relay's public REST API allows 600 requests per minute per workspace token. Burst traffic above the limit receives HTTP 429 with a Retry-After header in seconds.

Bulk endpoints, such as task import, count as 10 requests each. The export endpoint is limited separately to 5 concurrent export jobs per workspace.

Clients should back off exponentially, starting at the Retry-After value. Repeated violations for more than 15 minutes trigger an alert to Relay's platform on-call engineer, who may contact the customer.
""",
    "webhook-delivery.md": """# Webhook Delivery and Retries

Workflow webhooks are delivered with an HMAC-SHA256 signature in the X-Relay-Signature header. Receivers must verify the signature using the webhook secret shown once at creation time.

Failed deliveries are retried 8 times with exponential backoff, the last attempt about 6 hours after the first. After the final failure the webhook is marked "degraded" and the workspace owner receives an email.

Webhook payloads never include attachment contents, only attachment IDs. Payloads larger than 256 KB are truncated and flagged with "truncated": true.
""",
    "data-retention.md": """# Data Retention Policy

Deleted tasks remain in the workspace trash for 30 days and can be restored by any admin. After 30 days they are permanently deleted from the primary database.

Database backups are kept for 35 days, so permanently deleted data disappears from backups within 35 days of permanent deletion.

Audit log entries are retained for 400 days on the Business plan and 90 days on the Team plan. Customers can export audit logs at any time through the admin console.
""",
    "sso-setup.md": """# Single Sign-On Setup

Relay supports SAML 2.0 and OpenID Connect. SSO is available on the Business plan only.

SAML signing certificates must be rotated before they expire; Relay warns workspace owners 30 days and 7 days before expiry. If a certificate expires, all SSO logins fail until a new certificate is uploaded.

SSO sessions last 12 hours by default. Admins can shorten the session length to as little as 15 minutes in Security settings, which is a common cause of "logged out every 15 minutes" reports.
""",
    "deploy-schedule.md": """# Deployment Schedule

Relay deploys to production every weekday at 15:00 UTC through the deploy train. Changes merged after 14:00 UTC wait for the next day's train.

Hotfixes may deploy outside the train with approval from the on-call engineer and one tech lead. Every hotfix must be followed by a post-incident review within 5 working days.

Production deploys are frozen from 20 December to 2 January, except for security fixes approved by the head of engineering.
""",
    "oncall-escalation.md": """# On-Call Escalation

P1 incidents page the platform on-call engineer immediately. If the page is not acknowledged within 10 minutes, it escalates to the secondary on-call, and after 20 minutes to the engineering manager.

P2 incidents create a ticket for the owning team and must be acknowledged within 4 business hours. P3 and P4 issues go to the team's backlog.

Security incidents, including suspected data exposure, are always P1 and must also be reported to the security lead within 1 hour.
""",
    "billing-proration.md": """# Billing and Proration

Seats added mid-cycle are charged immediately, prorated to the end of the current billing period. Seats removed mid-cycle are credited to the next invoice, not refunded.

Switching from monthly to annual billing takes effect at the next renewal date, and the annual price includes a 15% discount. Tax is calculated from the billing address, so changing the address can change the tax charged.

Failed card payments are retried 3 times over 7 days. After the third failure the workspace becomes read-only until payment succeeds.
""",
    "export-limits.md": """# Exports

Project exports are available as CSV or JSON. A single export includes up to 50,000 tasks; larger projects must be exported in date ranges.

Exports run as background jobs and are available for download for 7 days. A known issue causes exports started during a deploy to omit tasks changed in the final minute; re-running the export after the deploy completes avoids it.

Attachments are not included in exports. Use the API to download attachments separately.
""",
    "api-tokens.md": """# API Tokens

Personal API tokens inherit the permissions of the user who created them. Changing or resetting that user's password revokes all of their personal tokens immediately.

For integrations, Relay recommends service tokens, which belong to the workspace rather than a person and survive password changes. Service tokens can be scoped to read-only or read-write, per project.

Tokens are shown only once at creation. Relay stores a hash, not the token, so lost tokens cannot be recovered and must be replaced.
""",
    "timezones.md": """# Dates and Time Zones

Relay stores all timestamps in UTC and converts them to the viewer's time zone for display. Due dates without a time are stored as dates, not timestamps.

A known defect affects users in time zones more than 12 hours ahead of UTC, such as Pacific/Auckland during daylight saving: due dates can display one day early. The fix is scheduled for the 4.18 release.

Recurring tasks use the time zone of the person who created the recurrence, not the assignee.
""",
    "roles-permissions.md": """# Roles and Permissions

Relay has four workspace roles: Owner, Admin, Member and Guest. There is exactly one Owner per workspace; ownership can be transferred but not shared.

Admins can manage members, projects and integrations, but only the Owner can see the Billing tab, change the plan or delete the workspace.

Guests can access only the projects they are explicitly invited to and cannot see the member directory. For contractors, Relay recommends the Guest role with access limited to the relevant projects.
""",
    "notifications.md": """# Notifications

Users receive email notifications for mentions, assignments and due-date reminders. Each type can be turned off individually in Profile settings, under Notifications.

If a user marks Relay emails as spam, the mail provider may stop delivering them; Relay then suppresses further emails to that address for 30 days to protect its sending reputation.

Workspace admins can set default notification preferences for new members but cannot override a user's own settings.
""",
}

# "keyword" questions reuse the document's own words. "paraphrase" questions
# ask the same kind of thing the way a customer would, without the
# document's vocabulary. Keyword retrieval handles the first kind well and
# the second kind badly; the lab measures both.
QUESTIONS = [
    ("Q01", "How many API requests per minute does a workspace token allow?", "600", "api-rate-limits.md"),
    ("Q02", "How many requests does a single bulk task import count as against the rate limit?", "10 requests", "api-rate-limits.md"),
    ("Q03", "How many times is a failed webhook delivery retried?", "8 times", "webhook-delivery.md"),
    ("Q04", "Which header carries the webhook signature?", "X-Relay-Signature", "webhook-delivery.md"),
    ("Q05", "How long do deleted tasks stay in the trash?", "30 days", "data-retention.md"),
    ("Q06", "How long are audit logs retained on the Team plan?", "90 days", "data-retention.md"),
    ("Q07", "What is the shortest SSO session length an admin can configure?", "15 minutes", "sso-setup.md"),
    ("Q08", "What happens to SSO logins when the SAML certificate expires?", "all SSO logins fail", "sso-setup.md"),
    ("Q09", "At what time does the production deploy train run?", "15:00 UTC", "deploy-schedule.md"),
    ("Q10", "Within how many working days must a post-incident review follow a hotfix?", "5 working days", "deploy-schedule.md"),
    ("Q11", "After how many minutes does an unacknowledged P1 page escalate to the secondary on-call?", "10 minutes", "oncall-escalation.md"),
    ("Q12", "Within what time must suspected data exposure be reported to the security lead?", "1 hour", "oncall-escalation.md"),
    ("Q13", "What discount does annual billing include?", "15%", "billing-proration.md"),
    ("Q14", "What happens to the workspace after the third failed card payment?", "read-only", "billing-proration.md"),
    ("Q15", "What is the maximum number of tasks in a single export?", "50,000", "export-limits.md"),
    ("Q16", "Why might an export miss tasks changed in the final minute?", "during a deploy", "export-limits.md"),
    ("Q17", "What happens to personal API tokens when the user's password is reset?", "revokes", "api-tokens.md"),
    ("Q18", "Which kind of token survives password changes?", "service tokens", "api-tokens.md"),
    ("Q19", "In which release is the early due-date display fix scheduled?", "4.18", "timezones.md"),
    ("Q20", "Whose time zone do recurring tasks use?", "the person who created the recurrence", "timezones.md"),
    ("Q21", "Which role can see the Billing tab?", "only the Owner", "roles-permissions.md"),
    ("Q22", "Which role does Relay recommend for contractors?", "Guest role", "roles-permissions.md"),
    ("Q23", "For how long does Relay suppress emails after a user marks them as spam?", "30 days", "notifications.md"),
    ("Q24", "Can workspace admins override a user's own notification settings?", "cannot override", "notifications.md"),
]

PARAPHRASES = [
    ("P01", "If our integration sends too many calls, what status code comes back?", "HTTP 429", "api-rate-limits.md"),
    ("P02", "How do I check that a webhook call really came from Relay?", "HMAC-SHA256", "webhook-delivery.md"),
    ("P03", "Once something is purged from the bin, how long until it is also gone from backups?", "35 days", "data-retention.md"),
    ("P04", "Our auditors want a full year of login history. Which plan keeps it long enough?", "Business plan", "data-retention.md"),
    ("P05", "Why do people on our team keep getting signed out a quarter of an hour after signing in?", "15 minutes", "sso-setup.md"),
    ("P06", "Can we ship an urgent fix on a Saturday night?", "approval from the on-call engineer", "deploy-schedule.md"),
    ("P07", "Who gets woken up first when production is completely down?", "platform on-call engineer", "oncall-escalation.md"),
    ("P08", "We added five people halfway through the month. When do we pay for them?", "charged immediately", "billing-proration.md"),
    ("P09", "Our project has 80,000 tasks. Can we download them all at once?", "date ranges", "export-limits.md"),
    ("P10", "Our nightly sync broke after someone changed their password. What should the integration use instead?", "service tokens", "api-tokens.md"),
    ("P11", "Customers in New Zealand see deadlines a day early. Is this known?", "4.18", "timezones.md"),
    ("P12", "Can a freelancer be kept out of our staff list?", "cannot see the member directory", "roles-permissions.md"),
]


# Held out: written AFTER the synonym map below was frozen, and never used to
# tune it. Results on these questions show how well the map generalizes; results
# on PARAPHRASES are optimistic because the map was built while reading them.
HELDOUT = [
    ("H01", "What's the most we can call the API each minute?", "600", "api-rate-limits.md"),
    ("H02", "Do webhook payloads carry the files people attached?", "only attachment IDs", "webhook-delivery.md"),
    ("H03", "How many days do we have to restore something we deleted by mistake?", "30 days", "data-retention.md"),
    ("H04", "When will Relay warn us before our identity provider certificate runs out?", "30 days and 7 days", "sso-setup.md"),
    ("H05", "Is there a period at the end of the year when you don't release changes?", "20 December to 2 January", "deploy-schedule.md"),
    ("H06", "How fast must a medium-severity issue be picked up by a team?", "4 business hours", "oncall-escalation.md"),
    ("H07", "If we drop seats in the middle of a billing period, do we get money back?", "credited to the next invoice", "billing-proration.md"),
    ("H08", "How long do finished exports stay available to grab?", "7 days", "export-limits.md"),
    ("H09", "Can two people share ownership of a workspace?", "ownership can be transferred but not shared", "roles-permissions.md"),
    ("H10", "Will Relay keep emailing someone who flagged its messages as junk?", "suppresses further emails", "notifications.md"),
]

# Customer words mapped to the words Relay's docs use. In production a team
# curates this from search logs, or asks an LLM to rewrite the query; here it
# is fixed so results are reproducible.
SYNONYMS = {
    "calls": ["requests"], "status": ["http"], "code": ["http"],
    "check": ["verify", "signature"], "came": ["signature"],
    "purged": ["permanently", "deleted"], "bin": ["trash"],
    "auditors": ["audit"], "login": ["audit", "log"], "history": ["log", "retained"], "year": ["400", "days"],
    "signed": ["logged", "session", "sso"], "quarter": ["15"], "hour": ["minutes"],
    "ship": ["deploy", "hotfixes"], "saturday": ["train", "weekday"], "urgent": ["hotfixes"],
    "woken": ["page", "on", "call"], "production": ["p1", "incidents"], "down": ["p1"],
    "people": ["seats"], "halfway": ["mid", "cycle"], "pay": ["charged", "prorated"],
    "download": ["export", "exports"], "80": ["50"],
    "sync": ["integration", "tokens"],
    "zealand": ["auckland", "time", "zone"], "deadlines": ["due", "dates"],
    "freelancer": ["contractors", "guest"], "staff": ["member", "directory"], "list": ["directory"],
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "data"
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for name, text in DOCS.items():
        # newline="\n": the same bytes on every platform, so CI's reproducibility check passes on Linux and Windows.
        (docs_dir / name).write_text(text, encoding="utf-8", newline="\n")
    with (root / "questions.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for kind, items in (("keyword", QUESTIONS), ("paraphrase", PARAPHRASES), ("heldout", HELDOUT)):
            for qid, question, answer, source in items:
                if answer not in DOCS[source]:
                    raise SystemExit(f"{qid}: answer {answer!r} not found in {source}")
                record = {"id": qid, "type": kind, "question": question, "answer": answer, "source": source}
                f.write(json.dumps(record) + "\n")
    (root / "synonyms.json").write_text(json.dumps(SYNONYMS, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(DOCS)} documents and {len(QUESTIONS) + len(PARAPHRASES) + len(HELDOUT)} questions to {root}")


if __name__ == "__main__":
    main()

"""Write Lab 6.1's data/ folder. Deterministic: byte-identical on every platform.

    python scripts/generate_data.py

The drivers come from Chapter 4's approved PRD (ESC-N01 to ESC-N10, decisions
D1 to D9; labs/ch04/L4.1-brief-to-prd/data/prd-v1.md) plus six architecture
constraints from Relay's canonical facts. Three options are scored: A (modular
monolith with an asynchronous worker), B (microservices) and C (the monolith
with triage as one separate service). Weights and scores are the
architect's judgements (sam.o), each with a reason; the scoring tool only
does the arithmetic. They are inputs, not findings.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
PRD = "labs/ch04/L4.1-brief-to-prd/data/prd-v1.md"

PEOPLE = ["aisha.r", "lena.k", "priya.n", "sam.o", "tomas.b"]

DECISIONS = {
    "D1": "First P1 step at 10 minutes by default, configurable",
    "D2": "Only Owners and Admins edit rules",
    "D3": "A suggested priority never starts an escalation",
    "D4": "Business hours belong to the rule",
    "D5": "No SMS in version 1; a webhook event instead",
    "D6": "Targets are named users; no rotas in version 1",
    "D7": "Flood cap of 20 escalation emails per target per hour",
    "D8": "Numeric targets that no source states",
    "D9": "Acknowledgement ends escalation, and fired steps do not repeat",
}


def nfr(id_, category, title, weight, must=False, note=""):
    return {"id": id_, "kind": "nfr", "category": category, "title": title, "weight": weight,
            "must": must, "source": PRD, "note": note}


def con(id_, title, weight, source, must=False, note=""):
    return {"id": id_, "kind": "constraint", "category": "constraint", "title": title, "weight": weight,
            "must": must, "source": source, "note": note}


DRIVERS = {
    "version": "relay-drivers-2026.11",
    "scored_by": "sam.o",
    "scale": {"0": "cannot meet", "1": "meets only with high risk or effort",
              "2": "meets", "3": "meets with margin"},
    "must_rule": ("A must driver is one of the PRD's prohibitions (who decides priority, who changes rules, where "
                  "data goes, what is paid for) or CON-4. Thresholds the PRD marks for review after the pilot (D7, D8) "
                  "are weighted, not musts."),
    "people": PEOPLE,
    "decisions": DECISIONS,
    "drivers": [
        nfr("ESC-N01", "human-ai", "Suggested priorities need a person", 3, must=True),
        nfr("ESC-N02", "human-ai", "Confidence that means something", 0,
            note="Not architecture-significant: met by the triage evaluation (Chapter 7), whatever the structure."),
        nfr("ESC-N03", "security", "Rule permissions enforced on the server; every change audited for 400 days",
            3, must=True),
        nfr("ESC-N04", "abuse", "At most 20 escalation emails per target per hour, across all rules", 2),
        nfr("ESC-N05", "abuse", "Targets are workspace user IDs only", 1, must=True),
        nfr("ESC-N06", "abuse", "Owner and Admins emailed within 5 minutes of a P1 rule change", 2),
        nfr("ESC-N07", "privacy", "No task title, description or comments in emails or webhook events", 3,
            must=True),
        nfr("ESC-N08", "accessibility", "Rule editor meets WCAG 2.2 AA; keyboard only", 0,
            note="Not architecture-significant: a property of the editor's interface, the same in every option."),
        nfr("ESC-N09", "operability", "95% of steps within 60 seconds; a stalled evaluator pages after 5 minutes",
            3),
        nfr("ESC-N10", "cost", "$0 per notification beyond email and webhooks; no paid messaging service", 2,
            must=True),
        con("CON-1", "Operable by Relay's eight engineers on one platform on-call rota", 3,
            "Chapter 1 (team of eight engineers); Lab 2.2 docs (on-call)"),
        con("CON-2", "Ships on the daily deploy train, every weekday at 15:00 UTC", 2,
            "Chapter 1 recommendation; Lab 2.2 docs"),
        con("CON-3", "API limit of 600 requests per minute per token, HTTP 429 with Retry-After", 1,
            "Lab 2.2 docs (API)"),
        con("CON-4", "No API request waits for the triage model; API p95 under 1 second", 3,
            "sam.o, recorded in ADR-007; the model's p95 is 4.12 s in Chapter 2's evaluation", must=True),
        con("CON-5", "Webhook deliveries signed, retried 8 times over about 6 hours, safe to receive twice", 2,
            "Lab 2.2 docs (webhooks)"),
        con("CON-6", "Triage capacity can grow without growing the rest of Relay", 1,
            "sam.o, recorded in ADR-007"),
    ],
}


def comp(id_, name, kind, deployable=None):
    return {"id": id_, "name": name, "kind": kind, "deployable": deployable}


def flow(src, dst, data, boundary=None, sync=True):
    return {"from": src, "to": dst, "sync": sync, "boundary": boundary, "data": data}


OPTION_A = {
    "id": "A",
    "name": "Modular monolith with an asynchronous triage worker",
    "summary": ("One codebase and one deployable artifact, run as two process types: the HTTP service and "
                "the worker. One database; each module owns its tables. Triage runs from a durable queue "
                "table, so no request waits for the model."),
    "components": [
        comp("client", "Browsers, API clients and the support inbox", "external"),
        comp("web", "relay.service: HTTP service", "process", "relay"),
        comp("worker", "relay.worker: triage worker (later also the escalation evaluator)", "process", "relay"),
        comp("db", "Relay database: tasks, rules, triage_jobs; tables owned by modules", "datastore"),
        comp("model", "Triage model provider (hosted)", "external"),
        comp("email", "Email delivery provider", "external"),
        comp("hooks", "Customer webhook endpoints", "external"),
    ],
    "flows": [
        flow("client", "web", "requests, bearer tokens, ticket text", "TB1"),
        flow("web", "db", "task reads, triage job inserts"),
        flow("worker", "db", "job claims, suggestions, step state"),
        flow("worker", "model", "ticket text out; suggested labels back", "TB2"),
        flow("worker", "email", "escalation emails: link, priority, rule, step; never the title", "TB3"),
        flow("worker", "hooks", "signed task.escalated events", "TB4"),
    ],
    "boundaries": {
        "TB1": "Internet to the Relay service",
        "TB2": "Relay to the model provider",
        "TB3": "Relay to the email provider",
        "TB4": "Relay to customer webhook endpoints",
    },
    "step_path": ["worker", "db"],
    "scores": {
        "ESC-N01": [3, "The worker writes suggestions to its own table and never touches a task; one fitness "
                       "test checks that no module but the service reaches the worker, and code review sees "
                       "every path in one repository."],
        "ESC-N03": [2, "One permission module (relay.roles) and one audit table serve every route; the 400-day "
                       "retention is one setting on one database."],
        "ESC-N04": [3, "The cap counts emails per target across all rules; with one database the count and the "
                       "send are in one transaction."],
        "ESC-N05": [2, "Target validation lives in one module; either option can do it."],
        "ESC-N06": [2, "A rule change and its notification are written in one transaction; the worker sends it."],
        "ESC-N07": [2, "Task titles never leave the process except as a link; one place to test."],
        "ESC-N09": [2, "One worker heartbeat and one queue to watch; the 5-minute stall flag is in /healthz."],
        "ESC-N10": [2, "Calls only email and webhook delivery; no new paid service."],
        "CON-1": [3, "One artifact, one pipeline, one database and one set of dashboards for one rota."],
        "CON-2": [3, "One artifact on the daily train; a change across modules ships as one change."],
        "CON-3": [2, "The limiter is in the service; exact for one process, needs shared storage for several "
                     "(a recorded consequence)."],
        "CON-4": [3, "POST /v1/triage-jobs inserts a row and returns 202; the model is called by the worker."],
        "CON-5": [2, "Webhook sends are jobs with idempotency keys; receivers get the same delivery ID twice."],
        "CON-6": [2, "Worker processes scale separately from web processes, from the same artifact."],
    },
}

OPTION_B = {
    "id": "B",
    "name": "Microservices with a message broker",
    "summary": ("Five services, each deployed and scaled on its own with its own database: an API gateway, "
                "tasks, escalation, triage and notification. Services publish events to a message broker that "
                "the team runs itself."),
    "components": [
        comp("client", "Browsers, API clients and the support inbox", "external"),
        comp("gateway", "API gateway: authentication and rate limits", "process", "gateway"),
        comp("tasks", "tasks-svc", "process", "tasks-svc"),
        comp("escalation", "escalation-svc: rules and the evaluator", "process", "escalation-svc"),
        comp("triage", "triage-svc", "process", "triage-svc"),
        comp("notify", "notify-svc: email and webhooks", "process", "notify-svc"),
        comp("broker", "Self-hosted message broker, run by the team", "broker"),
        comp("tasks-db", "tasks database", "datastore"),
        comp("escalation-db", "escalation database", "datastore"),
        comp("triage-db", "triage database", "datastore"),
        comp("notify-db", "notification database", "datastore"),
        comp("model", "Triage model provider (hosted)", "external"),
        comp("email", "Email delivery provider", "external"),
        comp("hooks", "Customer webhook endpoints", "external"),
    ],
    "flows": [
        flow("client", "gateway", "requests, bearer tokens, ticket text", "TB1"),
        flow("gateway", "tasks", "requests with forwarded identity", "TB5"),
        flow("gateway", "escalation", "requests with forwarded identity", "TB5"),
        flow("gateway", "triage", "ticket text", "TB5"),
        flow("escalation", "tasks", "acknowledgement and project-visibility checks", "TB5"),
        flow("tasks", "tasks-db", "tasks"),
        flow("escalation", "escalation-db", "rules, step state, flood-cap counts"),
        flow("triage", "triage-db", "jobs and suggestions"),
        flow("notify", "notify-db", "deliveries and flood-cap counts"),
        flow("tasks", "broker", "task.priority_set events (with titles unless filtered)", "TB6", sync=False),
        flow("triage", "broker", "triage.suggested events", "TB6", sync=False),
        flow("escalation", "broker", "step.fired events", "TB6", sync=False),
        flow("broker", "notify", "step.fired events", "TB6", sync=False),
        flow("triage", "model", "ticket text out; suggested labels back", "TB2"),
        flow("notify", "email", "escalation emails", "TB3"),
        flow("notify", "hooks", "signed task.escalated events", "TB4"),
    ],
    "boundaries": {
        "TB1": "Internet to the API gateway",
        "TB2": "triage-svc to the model provider",
        "TB3": "notify-svc to the email provider",
        "TB4": "notify-svc to customer webhook endpoints",
        "TB5": "Gateway and services on the internal network",
        "TB6": "Services to the message broker",
    },
    "step_path": ["escalation", "escalation-db", "tasks", "tasks-db", "broker", "notify", "notify-db"],
    "scores": {
        "ESC-N01": [2, "triage-svc publishes suggestions as events; every consumer must ignore unconfirmed ones, "
                       "a rule kept by contract between services rather than in one place."],
        "ESC-N03": [1, "Each service checks permissions itself or calls a shared one; audit entries are spread "
                       "across four databases, each needing 400-day retention."],
        "ESC-N04": [1, "A cap across all rules needs one count shared by escalation-svc and notify-svc; a "
                       "distributed counter or a second source of truth."],
        "ESC-N05": [2, "Target validation lives in escalation-svc; either option can do it."],
        "ESC-N06": [2, "The rule change and its notification cross the broker; the outbox pattern makes it "
                       "reliable at extra cost."],
        "ESC-N07": [1, "Task content crosses the internal network and the broker; every consumer and the broker's "
                       "retention must keep titles out of outbound messages."],
        "ESC-N09": [2, "Each service fails on its own, but a step needs seven components up to fire; more "
                       "dashboards to watch."],
        "ESC-N10": [1, "A self-hosted broker is not a paid messaging service, but it joins the services escalation "
                       "calls, so ESC-AC31's list of only email and webhooks would need amending."],
        "CON-1": [1, "Five pipelines, four databases and a broker for one rota of eight; each service needs an "
                     "owner on call."],
        "CON-2": [1, "Five deploys a day on one train; a cross-service change needs versioned contracts and an "
                     "ordered rollout."],
        "CON-3": [3, "The gateway is the natural single place for the limit."],
        "CON-4": [3, "The gateway hands tickets to triage-svc asynchronously; no request waits for the model."],
        "CON-5": [2, "notify-svc owns deliveries and retries; the same idempotency rule applies."],
        "CON-6": [3, "triage-svc scales on its own, without scaling the other four services."],
    },
}

OPTION_C = {
    "id": "C",
    "name": "Modular monolith with a separate triage service",
    "summary": ("Relay's service and its escalation worker stay one artifact with one database, as in Option A. "
                "Triage moves into its own deployable service with its own database; Relay's service calls it over "
                "the internal network to queue tickets and read suggestions."),
    "components": [
        comp("client", "Browsers, API clients and the support inbox", "external"),
        comp("web", "relay.service: HTTP service", "process", "relay"),
        comp("worker", "relay.worker: escalation evaluator", "process", "relay"),
        comp("db", "Relay database: tasks, rules; tables owned by modules", "datastore"),
        comp("triage", "triage-svc: queue, worker and model adapter", "process", "triage-svc"),
        comp("triage-db", "triage database", "datastore"),
        comp("model", "Triage model provider (hosted)", "external"),
        comp("email", "Email delivery provider", "external"),
        comp("hooks", "Customer webhook endpoints", "external"),
    ],
    "flows": [
        flow("client", "web", "requests, bearer tokens, ticket text", "TB1"),
        flow("web", "db", "task reads"),
        flow("worker", "db", "step state"),
        flow("web", "triage", "ticket text out; suggestions back", "TB5"),
        flow("triage", "triage-db", "jobs and suggestions"),
        flow("triage", "model", "ticket text out; suggested labels back", "TB2"),
        flow("worker", "email", "escalation emails: link, priority, rule, step; never the title", "TB3"),
        flow("worker", "hooks", "signed task.escalated events", "TB4"),
    ],
    "boundaries": {
        "TB1": "Internet to the Relay service",
        "TB2": "triage-svc to the model provider",
        "TB3": "Relay to the email provider",
        "TB4": "Relay to customer webhook endpoints",
        "TB5": "Relay service to triage-svc on the internal network",
    },
    "step_path": ["worker", "db"],
    "scores": {
        "ESC-N01": [2, "Suggestions come back over an API, and Relay must store them as suggestions only: a rule kept "
                       "at the boundary between two codebases, checked by a contract test rather than one module."],
        "ESC-N03": [2, "Rules stay in the monolith with relay.roles and one audit table; triage-svc needs its own "
                       "service authentication, but holds no rules."],
        "ESC-N04": [3, "The flood cap stays in the monolith's one database, counted and sent in one transaction."],
        "ESC-N05": [2, "Target validation lives in one module, as in Option A."],
        "ESC-N06": [2, "A rule change and its notification are written in one transaction, as in Option A."],
        "ESC-N07": [2, "Task titles stay in the monolith; only ticket text crosses TB5 to triage-svc."],
        "ESC-N09": [2, "The step path is Option A's; triage-svc is one more service to watch."],
        "ESC-N10": [2, "No broker; escalation calls only email and webhook delivery."],
        "CON-1": [2, "Two deployables and two databases for one rota: workable, but triage-svc needs its own pipeline, "
                     "dashboards and runbook."],
        "CON-2": [2, "Two artifacts on the train; a change to the triage API needs both deployed in order."],
        "CON-3": [2, "The limiter stays in Relay's service, as in Option A."],
        "CON-4": [3, "Relay's service queues the ticket at triage-svc and returns 202; no request waits for the model."],
        "CON-5": [2, "Webhook sends stay jobs with idempotency keys in the monolith."],
        "CON-6": [3, "triage-svc scales on its own, without scaling the monolith."],
    },
}

SCENARIO = {
    "name": "five-teams",
    "description": ("Hypothetical, not a forecast: Relay has grown to five product teams of about eight engineers, "
                    "triage has its own team and on-call rota, and the company runs a shared identity service, a "
                    "shared rate-limit store and a platform team that operates the broker."),
    "titles": {
        "CON-1": "Operable by five product teams, each with its own on-call rota",
        "CON-2": "Each team ships its own changes on the daily deploy train",
        "CON-6": "Triage capacity can grow without growing the rest of Relay (triage now has its own team)",
    },
    "weights": {"CON-6": 3, "CON-2": 3},
    "scores": {
        "A": {"CON-1": [1, "One artifact and one rota shared by five teams; every incident pages people who did not "
                           "write the code."],
              "CON-2": [1, "Five teams' changes queue for one artifact on one train."]},
        "B": {"CON-1": [3, "Each team owns and runs its own services on its own rota."],
              "CON-2": [3, "Each team deploys its own services independently, on its own schedule."],
              "ESC-N03": [2, "The shared identity service checks permissions for every service."],
              "ESC-N04": [2, "The shared rate-limit store holds the count across all rules."],
              "ESC-N10": [2, "The platform team runs the broker as shared infrastructure, not a paid service."]},
        "C": {"CON-1": [3, "The triage team runs triage-svc on its own rota; the rest stays one artifact."],
              "CON-2": [3, "Triage deploys on its own; the monolith's teams share one artifact less often."]},
    },
}

ADR_DRAFT = """# ADR-007 — Relay service architecture

Status: proposed
Date: 2026-11-20
Decided by: relay-architect-agent
Links: D3, D10, ESC-N04, ESC-N11

## Context

Relay needs an HTTP service for escalation rules and a background process for ticket triage. The team wants the
architecture to be scalable, resilient and future-proof. Serverless functions were also mentioned.

## Options considered

### Option A — Modular monolith with an asynchronous triage worker

One application with a worker process and one database.

### Option B — Microservices

Separate services for tasks, escalation, triage and notification, communicating through a message broker. Each
service scales independently and each team can deploy on its own schedule.

## Decision

Option A, the modular monolith, because it is simpler for now.

## Rejected alternatives

### Option B — Microservices
Rejected because: too complex for now.
"""


def threat_model(option, author, reviewer, date, diagram, rows):
    lines = [f"# Threat model — Option {option['id']}: {option['name']}", "",
             f"Option: {option['id']}", f"Author: {author}", f"Reviewed by: {reviewer}", f"Date: {date}", "",
             "## Diagram", "", "```mermaid", *diagram, "```", "",
             "## Threats", "",
             "| # | Boundary | STRIDE | Threat | Control | Evidence |",
             "| ---: | --- | --- | --- | --- | --- |"]
    for n, (b, s, threat, control, evidence) in enumerate(rows, 1):
        lines.append(f"| {n} | {b} | {s} | {threat} | {control} | {evidence} |")
    return "\n".join(lines) + "\n"


DIAGRAM_A = [
    "flowchart LR",
    '    C["Clients"] -- "TB1" --> W["relay.service"]',
    "    subgraph R[\"Relay (one artifact, one trust zone)\"]",
    '        W --> DB[("Relay database")]',
    '        K["relay.worker"] --> DB',
    "    end",
    '    K -- "TB2" --> M["Model provider"]',
    '    K -- "TB3" --> E["Email provider"]',
    '    K -- "TB4" --> H["Customer webhooks"]',
]

ROWS_A = [
    ("TB1", "S", "A stolen or guessed token is used to read tasks",
     "Only SHA-256 token hashes stored; unknown tokens get 401; personal tokens revoked on password reset",
     "relay-repo tests/test_service_app.py::test_v1_routes_need_a_known_token"),
    ("TB1", "E", "A Guest reads a project they were not invited to through the API",
     "Every task route calls relay.roles before returning data",
     "test_service_app.py::test_task_view_goes_through_roles"),
    ("TB1", "D", "One token floods the service",
     "600 requests per minute per token with 429 and Retry-After; 16 KB body cap",
     "test_service_app.py::test_rate_limit_is_per_token_and_says_when_to_retry; ::test_body_validation"),
    ("TB1", "T", "A retried POST creates duplicate jobs, or a reused key swaps the body",
     "Idempotency-Key required; same key and body replays the job; a different body gets 422",
     "test_service_app.py::test_replay_with_same_key_returns_the_same_job; ::test_same_key_different_body_is_422"),
    ("TB1", "I", "Ticket text leaks through error messages or job views",
     "Errors and job views never echo the ticket",
     "test_service_app.py::test_errors_do_not_echo_the_ticket; ::test_job_view_never_contains_the_ticket_text"),
    ("TB1", "R", "A triage submission cannot be traced to the user who made it",
     "Jobs record workspace and idempotency key, not the user",
     "Residual risk, owner sam.o: add the submitting user to triage_jobs before the pilot"),
    ("TB2", "T", "An injected ticket steers the suggested priority",
     "Suggestions never apply themselves; a person confirms or overrides (D3, ESC-N01)",
     "tests/test_worker_runner.py::test_an_injected_ticket_can_steer_a_suggestion_but_nothing_applies_it"),
    ("TB2", "I", "Ticket text with customer data is sent to the model provider",
     "Provider's data-handling terms checked before any real data is sent (Chapter 2); synthetic tickets in labs",
     "Residual risk, owner aisha.r: provider terms review recorded before production use"),
    ("TB2", "D", "The model is slow or unavailable and triage stalls",
     "Durable queue; 10 s timeout; 3 attempts with backoff, then a person's queue; heartbeat and 5-minute stall flag",
     "test_worker_runner.py::test_slow_answer_is_a_timeout_and_is_retried; "
     "::test_unavailable_three_times_goes_to_a_person; ::test_stall_rule_is_five_minutes"),
    ("TB2", "T", "Malformed model output is stored as a suggestion",
     "Strict schema validation; nothing is repaired",
     "test_worker_runner.py::test_parse_suggestion_rejects_extra_fields_bad_enums_and_bad_confidence"),
    ("TB3", "I", "A task title leaves Relay in an escalation email",
     "Emails carry the link, priority, rule and step only (ESC-N07)",
     "Planned: ESC-AC27, written test-first in Chapter 8"),
    ("TB4", "S", "Customers accept forged task.escalated events",
     "HMAC-SHA256 signature in X-Relay-Signature, as for every Relay webhook",
     "Planned: ESC-AC15, written test-first in Chapter 8"),
    ("none", "E", "A compromised worker process reads or writes every table",
     "Module ownership enforced in code by fitness tests; one database role for both processes in 4.19.0",
     "Residual risk, owner sam.o: import rules do not constrain a compromised process; separate database roles "
     "(Chapter 11)"),
]

DIAGRAM_A_DRAFT = [
    "flowchart LR",
    '    C["Clients"] -- "TB1" --> W["relay.service"]',
    '    W --> DB[("Relay database")]',
    '    K["relay.worker"] --> DB',
    '    K -- "TB3" --> E["Email provider"]',
    '    K -- "TB4" --> H["Customer webhooks"]',
]

ROWS_A_DRAFT = [
    ("TB1", "S", "A stolen token is used to read tasks", "Token hashes; 401 on unknown tokens",
     "test_service_app.py::test_v1_routes_need_a_known_token"),
    ("TB1", "D", "One token floods the service", "Rate limit of 600 requests per minute", ""),
    ("TB3", "I", "A task title leaves Relay in an email", "Emails carry a link only (ESC-N07)",
     "Planned: ESC-AC27"),
    ("TB4", "S", "Forged webhook events", "HMAC-SHA256 signatures", "Planned: ESC-AC15"),
]

DIAGRAM_B = [
    "flowchart LR",
    '    C["Clients"] -- "TB1" --> G["API gateway"]',
    "    subgraph N[\"Internal network\"]",
    '        G -- "TB5" --> T["tasks-svc"]',
    '        G -- "TB5" --> X["escalation-svc"]',
    '        G -- "TB5" --> R["triage-svc"]',
    '        X -- "TB5" --> T',
    "    end",
    '    T -- "TB6" --> B[["Message broker"]]',
    '    R -- "TB6" --> B',
    '    X -- "TB6" --> B',
    '    B -- "TB6" --> NS["notify-svc"]',
    '    R -- "TB2" --> M["Model provider"]',
    '    NS -- "TB3" --> E["Email provider"]',
    '    NS -- "TB4" --> H["Customer webhooks"]',
]

ROWS_B = [
    ("TB1", "S", "A stolen or guessed token is used at the gateway", "Token hashes at the gateway; 401",
     "None yet: option not built"),
    ("TB1", "D", "One token floods the gateway", "Gateway rate limit, 600 per minute per token",
     "None yet: option not built"),
    ("TB1", "I", "Ticket text leaks through gateway error pages", "Gateway never echoes bodies",
     "None yet: option not built"),
    ("TB5", "S", "A compromised service calls another while claiming to be the gateway",
     "Service identity and mutual TLS between every pair of services",
     "None yet: needs workload identity (Chapter 14)"),
    ("TB5", "E", "A service skips the permission check that the gateway assumed it would make",
     "Every service calls relay.roles' equivalent; shared contract tests",
     "None yet: contract tests per service pair"),
    ("TB5", "R", "A request's actions cannot be traced across services",
     "Propagated request IDs and per-service audit logs, each kept 400 days",
     "None yet: tracing (Chapter 16)"),
    ("TB6", "I", "Task titles sit in broker topics and their retention",
     "Events carry IDs only; consumers fetch content they are allowed to see",
     "None yet: schema review of every event type"),
    ("TB6", "T", "A forged or replayed event fires a step twice",
     "Broker authentication per service; consumers deduplicate on event IDs",
     "None yet: idempotent consumers in four services"),
    ("TB6", "D", "The broker is down and no step fires",
     "Outbox tables in each producer; alerts on broker lag",
     "None yet: broker operated by the team"),
    ("TB2", "T", "An injected ticket steers the suggested priority",
     "Consumers ignore unconfirmed suggestions (D3)", "None yet: a contract rule in each consumer"),
    ("TB2", "I", "Ticket text with customer data is sent to the model provider",
     "Provider terms checked first (Chapter 2)", "Residual risk, owner aisha.r"),
    ("TB2", "D", "The model is slow and triage-svc backs up", "Queue and timeouts in triage-svc",
     "None yet: option not built"),
    ("TB3", "I", "A task title leaves Relay in an email", "notify-svc renders links only (ESC-N07)",
     "None yet: option not built"),
    ("TB4", "S", "Customers accept forged webhook events", "HMAC-SHA256 signatures in notify-svc",
     "None yet: option not built"),
]


DIAGRAM_C = [
    "flowchart LR",
    '    C["Clients"] -- "TB1" --> W["relay.service"]',
    "    subgraph R[\"Relay (one artifact)\"]",
    '        W --> DB[("Relay database")]',
    '        K["relay.worker"] --> DB',
    "    end",
    '    W -- "TB5" --> T["triage-svc"]',
    '    T --> TD[("triage database")]',
    '    T -- "TB2" --> M["Model provider"]',
    '    K -- "TB3" --> E["Email provider"]',
    '    K -- "TB4" --> H["Customer webhooks"]',
]

ROWS_C = [
    ("TB1", "S", "A stolen or guessed token is used to read tasks",
     "Only SHA-256 token hashes stored; unknown tokens get 401",
     "relay-repo tests/test_service_app.py::test_v1_routes_need_a_known_token"),
    ("TB1", "D", "One token floods the service", "600 requests per minute per token; 16 KB body cap",
     "test_service_app.py::test_rate_limit_is_per_token_and_says_when_to_retry"),
    ("TB1", "I", "Ticket text leaks through error messages", "Errors never echo the ticket",
     "test_service_app.py::test_errors_do_not_echo_the_ticket"),
    ("TB5", "S", "Another process on the internal network calls triage-svc as Relay",
     "Service identity and mutual TLS between Relay and triage-svc", "None yet: workload identity (Chapter 14)"),
    ("TB5", "I", "Ticket text is read in transit to triage-svc", "TLS on the internal network",
     "None yet: option not built"),
    ("TB5", "T", "triage-svc's answer is applied to a task", "Relay stores suggestions only (D3, ESC-N01)",
     "None yet: a contract test at TB5"),
    ("TB2", "T", "An injected ticket steers the suggested priority", "Suggestions only; a person confirms (D3)",
     "None yet: triage-svc's own tests"),
    ("TB2", "I", "Ticket text with customer data is sent to the model provider",
     "Provider terms checked first (Chapter 2)", "Residual risk, owner aisha.r"),
    ("TB2", "D", "The model is slow and triage-svc backs up", "Queue, timeouts and a person's queue in triage-svc",
     "None yet: option not built"),
    ("TB3", "I", "A task title leaves Relay in an email", "Emails carry the link, priority, rule and step only",
     "Planned: ESC-AC27, written test-first in Chapter 8"),
    ("TB4", "S", "Customers accept forged task.escalated events", "HMAC-SHA256 signature in X-Relay-Signature",
     "Planned: ESC-AC15, written test-first in Chapter 8"),
    ("none", "E", "A compromised escalation worker reads or writes every table in Relay's database",
     "One database role for the monolith's two processes",
     "Residual risk, owner sam.o: separate database roles (Chapter 11)"),
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    write(DATA / "drivers.json", dump(DRIVERS))
    write(DATA / "options" / "A-modular-monolith.json", dump(OPTION_A))
    write(DATA / "options" / "B-microservices.json", dump(OPTION_B))
    write(DATA / "options" / "C-monolith-plus-triage-service.json", dump(OPTION_C))
    write(DATA / "scenarios" / "five-teams.json", dump(SCENARIO))
    write(DATA / "adr" / "ADR-007-draft.md", ADR_DRAFT)
    write(DATA / "threat-models" / "A-modular-monolith.md",
          threat_model(OPTION_A, "priya.n", "aisha.r", "2026-11-23", DIAGRAM_A, ROWS_A))
    write(DATA / "threat-models" / "B-microservices.md",
          threat_model(OPTION_B, "priya.n", "aisha.r", "2026-11-23", DIAGRAM_B, ROWS_B))
    write(DATA / "threat-models" / "C-monolith-plus-triage-service.md",
          threat_model(OPTION_C, "priya.n", "aisha.r", "2026-11-23", DIAGRAM_C, ROWS_C))
    write(DATA / "threat-models" / "A-draft.md",
          threat_model(OPTION_A, "relay-architect-agent", "", "2026-11-20", DIAGRAM_A_DRAFT, ROWS_A_DRAFT))
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()

# Spec — Escalation rules engine

Spec: ESC-SPEC-1
Version: 1.1.0
Status: approved
Derived from: prd-v1.1.md@1.1
Risk: high
Product owner: lena.k
Tech lead: sam.o
Security reviewer: aisha.r
Approved by: lena.k, sam.o, aisha.r
Approved on: 2026-11-30
Relay release: 4.20.0

## Goals

- Decide, for any rule and task, exactly which steps fire and when: calendar minutes for P1 rules, business hours for P2 to P4 rules (PRD G1).
- Refuse every rule that PRD v1.1 forbids before it can be saved, on the server, and audit every change and every refusal (PRD G1, G3).
- Fire each due step once, and turn it into one email per target and one signed webhook event, with no task content in either (PRD G2, G3).
- Show people what the model suggested without ever letting the suggestion start an escalation (PRD G1).
- Give later stages versioned contracts: the documents (JSON Schema) and the HTTP routes (OpenAPI).

## Non-goals

- Carrying messages across TB3 and TB4. The engine writes emails and webhook events to its outbox; the delivery adapters that send them are separate modules, each with its own ADR (ADR-007, FF004). Suppressed addresses (ESC-R10, ESC-AC16) belong to the email adapter.
- Deleting rules and the loud notices for P1 rule changes (ESC-N06's ESC-AC25). They come with a later slice; until then no route deletes a rule.
- Comments and service tokens, which the snapshot does not have (ESC-AC04).
- The web client: the rule form's defaults (ESC-AC07) and its accessibility (ESC-N08, ESC-AC28). The engine's routes return what the client renders.
- Calibration of the model's confidence (ESC-N02), which Chapter 7's evaluation decides.
- Operability measures (ESC-N09): paging on a stalled evaluator and the weekly 95% check are runtime checks (Chapter 16).
- Calling `run_pass` from the worker's loop. 4.20.0 leaves `relay.worker` unchanged; ADR-011 records the call the worker will make.
- The P1 flood-cap exemption, an open question in PRD v1.1 (owner lena.k). Until it is decided, P1 escalation emails are capped like any other, as PRD v1.1 states.

## Actors

| Actor | Relay role | In this release |
| --- | --- | --- |
| Rule editor | Owner or Admin (D2) | Creates and replaces rules through `PUT .../escalation-rules/{rid}` |
| Rule reader | Owner, Admin or Member (D2) | Lists and reads a project's rules; Guests cannot |
| Priority setter | Owner, Admin or Member who can view the project (ESC-R01) | Sets or confirms a task's priority |
| Target | Any workspace user who can view the rule's project (ESC-R08) | Named by user ID; acknowledges the task |
| Triage model | Not a user | Its suggestion is stored for display only and never read by `evaluate` (D3) |
| Evaluation pass | Relay code (the worker, ADR-011) | Calls `run_pass` with the current UTC time |
| Delivery adapters | Relay code, outside this spec | Read the outbox and send its messages unchanged |

## Behavior

### B1 — Rule validation

Requirements: ESC-R03, ESC-R05, ESC-R07, ESC-R08, ESC-N05, ESC-N06

`validate_rule(rule, editor, project, users)` returns the rule unchanged if Relay may save it, and raises `RuleRejected` otherwise. It is a pure function. Checks run in this order, and the first failure is raised:

1. The editor (`not_rule_editor`).
2. The priority: one of P1, P2, P3, P4 (`unsupported_priority`).
3. Business hours: a P1 rule has none (`business_hours_not_allowed`); a P2 to P4 rule must have them (`business_hours_required`); they must name a supported zone, give HH:MM times with the start before the end, and list distinct ISO weekdays (`business_hours_invalid`).
4. At least one step (`no_steps`).
5. Each step in turn, all of step 1 before any of step 2: (a) its number (`steps_not_numbered`); (b) its delay's range (`delay_out_of_range`); (c) its delay against the previous step's (`delays_not_increasing`); (d) at least one target (`no_targets`); (e) each target in turn (`target_not_user`, `target_not_in_workspace`, `target_cannot_view_project`).

| Code | When | Criterion |
| --- | --- | --- |
| `not_rule_editor` | The editor is not an Owner or Admin (D2) | ESC-AC06 |
| `unsupported_priority` | The rule's priority is not P1, P2, P3 or P4 | – |
| `business_hours_required` | A P2, P3 or P4 rule has no business hours (ESC-R07) | – |
| `business_hours_not_allowed` | A P1 rule has business hours; P1 steps count calendar minutes (ESC-R04) | – |
| `business_hours_invalid` | Unknown zone, malformed time, start not before end, or bad days (D10, ADR-010) | – |
| `no_steps` | The rule has no steps | – |
| `steps_not_numbered` | Steps are not numbered 1, 2, ... in order | – |
| `delay_out_of_range` | A delay is not a whole number of minutes from 5 to 240; the message names the range (D1) | ESC-AC10 |
| `delays_not_increasing` | A step's delay is not greater than the previous step's (D1) | – |
| `no_targets` | A step has no targets (ESC-N06) | ESC-AC26 |
| `target_not_user` | A target is not an integer user ID, for example an email address (ESC-N05) | ESC-AC24 |
| `target_not_in_workspace` | A target ID is not a user in the workspace (ESC-N05) | – |
| `target_cannot_view_project` | A target cannot view the rule's project; the message names the user (ESC-R08) | ESC-AC14 |

### B2 — Rule evaluation

Requirements: ESC-R01, ESC-R04, ESC-R06, ESC-N01, ESC-N07

`evaluate(rule, task, state, now)` decides which of the rule's steps fire for one task at `now`, an aware UTC time. A step is due when its delay has elapsed since `priority_set_at`: calendar minutes for a P1 rule, business minutes (B3) for a P2 to P4 rule. It fires when `now` is at or after its due time. Every due step that has not already fired is returned, in step order. A step never fires twice (D9).

| Status | When |
| --- | --- |
| `not_applicable` | The task has no priority set by a person, or its priority differs from the rule's. A suggested priority never counts (D3) |
| `acknowledged` | The task has been acknowledged; its remaining steps are cancelled (D9) |
| `active` | At least one step has not yet fired after this evaluation |
| `complete` | Every step has fired, now or earlier |

### B3 — Business hours

Requirements: ESC-R07 (D4, D10, D11)

A rule's business hours are a local start and end time, a time zone and the ISO weekdays they apply (1 is Monday). A business minute is a real, elapsed minute inside a window: from the start to the end, on a listed day, in local wall-clock time in the rule's zone (D11). `add_business_minutes(start, minutes, hours)` returns the instant at which `minutes` business minutes have elapsed since `start`.

- A start outside a window waits for the next window's opening.
- A delay that elapses exactly as a window closes is due at the close, not at the next opening.
- Windows follow the zone's daylight-saving changes, so 06:00 to 22:00 stays 06:00 to 22:00 local time. Relay carries the changes for its 14 supported zones for 2026 and 2027, and raises an error outside those years rather than guess (ADR-010).

So a P2 set at 21:00 local time on a Tuesday, with hours 06:00 to 22:00 and one step at 240 business minutes, is due at 09:00 local time on Wednesday: 60 minutes on Tuesday and 180 on Wednesday. Set at 21:00 on a Friday with Monday-to-Friday hours, it is due at 09:00 on Monday.

### B4 — Rule changes and audit

Requirements: ESC-R03, ESC-N03, ESC-N05

`save_rule` validates on the server (B1) and saves the rule with an audit entry: who, when, the rule before and after. A refused change leaves the saved rule unchanged and is audited as refused, with its code. Refusals before validation are audited too: an editor without the role (`not_rule_editor`), a document that breaks the contract (`invalid_document`, with the failing field paths but not their values), and a rule ID already used in another project (`rule_id_in_use`). Rule IDs are unique in a workspace.

### B5 — The evaluation pass and delivery

Requirements: ESC-R04, ESC-R06, ESC-R09, ESC-R11, ESC-N04, ESC-N07, ESC-N10

`run_pass(store, tasks, projects, config, now)` evaluates every saved rule for every task with a person-set priority and no acknowledgement. For each step that fires, in one transaction with recording the step as fired:

- one escalation email per target, unless the target has received 20 escalation emails in the 60 minutes before `now` (ESC-N04, D7). Then the email is held, the task's activity records it as not emailed, and the target receives one summary email listing every held escalation when the clock hour ends (UTC);
- one `task.escalated` webhook event per step, whatever the number of targets, if the workspace has a webhook. Webhook events are not capped;
- each message names the rule, the step, the time its delay started and the time it fired, in UTC (ESC-R11), and carries the task's link, its priority and the project's name (ESC-N07). It carries no task title, description or comment, and no email address: the email adapter resolves `to_user` inside Relay.

The event body is compact JSON with sorted keys, and its `X-Relay-Signature` header is `sha256=` followed by the hex HMAC-SHA256 of exactly those bytes under the workspace's webhook secret (SEC-06).

### B6 — Priorities, suggestions and acknowledgement

Requirements: ESC-R01, ESC-R02, ESC-N01

`set_priority` records a priority set or confirmed by a person and restarts the rule clock; an override is a person setting a different priority. `record_suggestion` stores the triage model's suggestion and confidence for display only; anything but P1 to P4 and a whole-number percentage from 0 to 100 is refused, and nothing is stored. `acknowledge` records the first acknowledgement by a person who can view the project. `escalation_view` returns what the task shows: the priority, who set it and when, the suggestion as "Suggested: P1 (91%)", the acknowledgement and the escalation activity.

### B7 — HTTP routes

Requirements: ESC-R01, ESC-R02, ESC-R03, ESC-N03, ESC-N05

| Route | Who | Success | Refusals |
| --- | --- | --- | --- |
| `GET /v1/projects/{pid}/escalation-rules` | Owner, Admin, Member | 200 | 401; 403 Guest or project not visible; 404; 429 |
| `GET /v1/projects/{pid}/escalation-rules/{rid}` | Owner, Admin, Member | 200 | 401; 403; 404 unknown rule or another project's; 429 |
| `PUT /v1/projects/{pid}/escalation-rules/{rid}` | Owner, Admin | 201 created, 200 replaced | 400 bad JSON or contract; 401; 403 not an editor; 404; 409 rule ID in use; 411; 413; 422 refused by B1; 429 |
| `GET /v1/projects/{pid}/tasks/{tid}/escalation` | Anyone who can view the project | 200 | 401; 403; 404; 429 |
| `POST /v1/projects/{pid}/tasks/{tid}/priority` | Owner, Admin, Member who can view the project | 200 | 400; 401; 403; 404; 411; 413; 429 |
| `POST /v1/projects/{pid}/tasks/{tid}/acknowledge` | Anyone who can view the project | 200 | 401; 403; 404; 429 |

A `PUT` is checked in this order: authentication, rate limit, project, role (403, audited), body (411, 413, 400), contract (400, audited), path and body agree (400, audited), then `save_rule`. A 422 body is a `Rejection` document. Error bodies never echo request values.

### Terms at this boundary

A step **fires** when `run_pass` records it as fired. Relay **notifies** a target, or **sends** an email or event, when the engine commits the message to its outbox in the same transaction; the delivery adapters carry outbox messages across TB3 and TB4 unchanged and are outside this spec. A rule **saves** when `save_rule` stores it, and Relay **refuses** when it raises `RuleRejected` or a route returns 4xx; a refused rule is **unchanged**. The task **shows** what `escalation_view` returns, and the **audit log** is the engine's audit table. A **part** of a title is any of its words of three or more letters or digits; the task's own ID, which the link must carry, is not counted.

## Non-functional requirements

| Source | Requirement in this release | How it is checked |
| --- | --- | --- |
| ESC-N01 | `evaluate` never reads the triage model's suggestion; suggestions never set a priority | ESC-AC18, ESC-AC19; policy test SEC-03; fuzz test of suggestions |
| ESC-N03 | Permissions enforced on the server; every change and refusal audited | ESC-AC21, ESC-AC22, ESC-AC24; test_SEC07 |
| ESC-N04 | At most 20 escalation emails per target per hour | ESC-AC23 |
| ESC-N05 | Targets are workspace user IDs only | ESC-AC24; the contract's integer targets |
| ESC-N07 | Messages carry no task content | ESC-AC27; policy test SEC-04 |
| ESC-N10 | The engine calls no service; it writes only email and webhook messages | ESC-AC31; policy test SEC-05 |
| Engine | Deterministic: every function takes the time as an argument | Every acceptance test passes a fixed time |
| Engine | Tests are independent of the code they test, and strong enough to kill seeded faults | test-strategy.md: oracle check and mutation score |

## Contracts

Contract: contracts/escalation-rules.schema.json
Outbound: Evaluation, StepDecision, EmailMessage, WebhookEvent

The document contract is a JSON Schema (2020-12) with eight definitions: `Rule`, `Step` and `BusinessHours` (in), `Evaluation` and `StepDecision` (out, from evaluation), `Rejection` (refusals, shown to the editor inside Relay), and `EmailMessage` and `WebhookEvent` (out, for delivery). Its `x-spec-version` must equal this spec's version. Relay validates documents with `relay.escalation.validate`, which implements only the keywords the contract uses and refuses any other.

The route contract is `contracts/escalation-api.openapi.json`, an OpenAPI 3.1 description of B7 whose request and response bodies reference the JSON Schema's definitions. A contract test compares it with the service's routes and status codes.

Changes in 1.1.0 are MINOR by caller compatibility: `Rule.priority` widens from P1 to P1–P4; `Rule.name` and `Rule.business_hours` are optional; the rejection codes, definitions and routes are new. Every rule 1.0.0 accepted is accepted, and evaluated, exactly as before. A P2 rule without business hours, refused in 1.0.0 with `unsupported_priority`, is now refused with `business_hours_required`.

## Data rules

Classes: Public; Internal (Relay staff and the workspace's own users); Confidential (customer content and personal data); Restricted (secrets and credentials).

| Field | Classification | Rule |
| --- | --- | --- |
| `Rule.rule_id` | Internal | – |
| `Rule.project_id` | Internal | – |
| `Rule.priority` | Internal | – |
| `Rule.steps` | Internal | – |
| `Rule.name` | Internal | Written by Owners and Admins and shown in messages; the editor says it must not contain customer data |
| `Rule.business_hours` | Internal | – |
| `Step.number` | Internal | – |
| `Step.delay_minutes` | Internal | Whole minutes, 5 to 240; business minutes for P2 to P4 rules |
| `Step.targets` | Internal | User IDs only, never addresses (ESC-N05) |
| `BusinessHours.start` | Internal | – |
| `BusinessHours.end` | Internal | – |
| `BusinessHours.time_zone` | Internal | – |
| `BusinessHours.days` | Internal | – |
| `Evaluation.spec_version` | Internal | – |
| `Evaluation.task_id` | Internal | The task is linked by ID; its content is not copied (ESC-N07) |
| `Evaluation.rule_id` | Internal | – |
| `Evaluation.evaluated_at` | Internal | UTC, whole seconds |
| `Evaluation.status` | Internal | – |
| `Evaluation.fire` | Internal | – |
| `Evaluation.next_due_at` | Internal | UTC, whole seconds |
| `StepDecision.step` | Internal | – |
| `StepDecision.targets` | Internal | User IDs; delivery resolves addresses inside Relay |
| `StepDecision.due_at` | Internal | UTC, whole seconds |
| `Rejection.code` | Internal | – |
| `Rejection.message` | Confidential | May name a user; shown only to the editor inside Relay, never emailed or logged outside it |
| `Rejection.subject` | Confidential | As `Rejection.message` |
| `EmailMessage.kind` | Internal | – |
| `EmailMessage.to_user` | Internal | A user ID; the email adapter resolves the address inside Relay (SEC-04) |
| `EmailMessage.subject` | Internal | Built only from Internal fields; no task content |
| `EmailMessage.body` | Internal | Built only from Internal fields; no task content |
| `WebhookEvent.event` | Internal | – |
| `WebhookEvent.spec_version` | Internal | – |
| `WebhookEvent.task_id` | Internal | – |
| `WebhookEvent.link` | Internal | Opening it needs a Relay login |
| `WebhookEvent.priority` | Internal | – |
| `WebhookEvent.project_name` | Internal | Workspace configuration, required by ESC-N07; not task content |
| `WebhookEvent.rule_id` | Internal | – |
| `WebhookEvent.rule_name` | Internal | As `Rule.name` |
| `WebhookEvent.step` | Internal | – |
| `WebhookEvent.targets` | Internal | User IDs |
| `WebhookEvent.delay_started_at` | Internal | UTC, whole seconds |
| `WebhookEvent.fired_at` | Internal | UTC, whole seconds |
| `Task.title` | Confidential | Never in a document for delivery (ESC-N07); no delivery function receives a Task |
| `User.name` | Confidential | Never in a document for delivery |
| `User.email` | Confidential | Never in a document for delivery; never a target (ESC-N05) |
| `EscalationState.suggested_priority` | Internal | Untrusted model output; never an input to evaluation (D3) |
| `Webhook.secret` | Restricted | Signs event bodies; never stored in the outbox, logged or sent |
| `AuditEntry.problems` | Internal | Field paths only, never the refused values |

## Security constraints

### SEC-01 — Only Owners and Admins change rules
Source: ESC-R03, ESC-N03, D2
Checks: ESC-AC06, ESC-AC21
Statement: `validate_rule` must refuse any editor who is not an Owner or Admin, and the service must refuse such a request with 403 before reading its body, whatever the client allows.

### SEC-02 — Targets are reachable workspace users
Source: ESC-R08, ESC-N05, ESC-N06
Checks: ESC-AC13, ESC-AC14, ESC-AC24, ESC-AC26
Statement: Every step must have at least one target, and every target must be the integer ID of a workspace user who can view the rule's project. An email address, phone number or URL is refused, by the contract on the server and by `validate_rule`.

### SEC-03 — A suggestion never starts an escalation
Source: ESC-N01, D3
Checks: ESC-AC18, ESC-AC19, test_SEC03
Statement: `evaluate` must read only the priority a person set. The triage model's suggestion is untrusted input, because a ticket's text can steer it: it is stored for display, it never sets a priority, and malformed suggestions are refused.

### SEC-04 — No task content in documents for delivery
Source: ESC-N07
Checks: ESC-AC27, test_SEC04
Statement: Every field of `Evaluation`, `StepDecision`, `EmailMessage` and `WebhookEvent` must be classified Internal or Public. No function that builds a message receives a `Task`, so none can copy its title.

### SEC-05 — The engine reaches nothing outside the process except its database
Source: ESC-N10 (refined)
Checks: ESC-AC31, test_SEC05
Statement: This constraint refines ESC-N10 into a rule a test can check, and the refinement is approved here by the security reviewer. The escalation package imports only the standard-library modules its policy test allows; only `store.py` imports `sqlite3`; nothing opens files, runs code from strings, starts processes or uses the network. The engine's only outputs to other services are outbox rows on the `email` and `webhook` channels.

### SEC-06 — Webhook events are signed, and the secret stays secret
Source: ESC-R09
Checks: ESC-AC15, test_SEC06
Statement: Every `task.escalated` event carries `X-Relay-Signature: sha256=<hex>`, the HMAC-SHA256 of the exact body bytes under the workspace's webhook secret. The secret is never written to the outbox, the audit log or an error.

### SEC-07 — Every escalation route refuses the unauthenticated, the unauthorized and the malformed
Source: ESC-N03, ESC-N05
Checks: ESC-AC21, ESC-AC24, test_SEC07
Statement: Every route in B7 has tests for a missing token, each role that must be refused, an object in a project the caller cannot view, and malformed or oversized bodies, and a fuzz test shows that no body produces a server error. Every refused rule change is audited without the refused values.

## Acceptance criteria

### ESC-AC01
Requirement: ESC-R01
Coverage: full
Criterion: Given a task with no priority, when a Member sets its priority to P1, then the task shows P1 and its activity records the Member and the time.

### ESC-AC02
Requirement: ESC-R01
Coverage: full
Criterion: Given a task with no priority and an active rule for its project, when 24 hours pass, then no step fires for the task.

### ESC-AC03
Requirement: ESC-R02
Coverage: full
Criterion: Given an unacknowledged P1 task, when its assignee selects Acknowledge, then the task records the assignee and the time as its acknowledgement.

### ESC-AC05
Requirement: ESC-R03
Coverage: full
Criterion: Given an Admin, when they save a P1 rule with two steps for a project, then the rule is active and appears in the project's rule list.

### ESC-AC06
Requirement: ESC-R03
Coverage: full
Criterion: Given a Member, when they try to save a change to a rule, then Relay refuses the change and the rule is unchanged.

### ESC-AC08
Requirement: ESC-R04
Coverage: full
Criterion: Given an active P1 rule with steps at 10 and 20 minutes, when a P1 task stays unacknowledged for 10 minutes, then the first step's targets are notified and the second step's targets are not.

### ESC-AC09
Requirement: ESC-R05
Coverage: full
Criterion: Given a P1 rule, when an Admin sets the first step's delay to 15 minutes, then the rule saves and the first step fires 15 minutes after a task's priority is set to P1.

### ESC-AC10
Requirement: ESC-R05
Coverage: full
Criterion: Given a P1 rule, when an Admin sets a step's delay to 4 minutes, then Relay refuses the change with a message that names the allowed range.

### ESC-AC11
Requirement: ESC-R06
Coverage: full
Criterion: Given a P1 task whose first step has fired, when a target acknowledges the task, then the second step does not fire.

### ESC-AC12
Requirement: ESC-R07
Coverage: full
Criterion: Given a P2 rule with business hours 06:00 to 22:00 in Europe/Berlin and one step at 4 business hours, when a task's priority is set to P2 at 21:00 local time and it stays unacknowledged, then the step fires at 09:00 local time the next day.

### ESC-AC13
Requirement: ESC-R08
Coverage: full
Criterion: Given a Guest invited to the Rotterdam project, when an Admin adds the Guest as a target of that project's P1 rule, then the rule saves.

### ESC-AC14
Requirement: ESC-R08
Coverage: full
Criterion: Given a Guest not invited to the Rotterdam project, when an Admin adds the Guest as a target of that project's rule, then Relay refuses the change and names the Guest.

### ESC-AC15
Requirement: ESC-R09
Coverage: full
Criterion: Given a workspace with one webhook and a step with two targets, when the step fires, then Relay sends two emails and one task.escalated event with an X-Relay-Signature header.

### ESC-AC17
Requirement: ESC-R11
Coverage: full
Criterion: Given a step whose delay started at 02:30 UTC and that fires at 02:40 UTC, when the target opens the escalation email, then it shows the rule's name, step 1, 02:30 UTC and 02:40 UTC.

### ESC-AC18
Requirement: ESC-N01
Coverage: full
Criterion: Given a task the triage model suggests as P1 with 91% confidence, when nobody confirms it for 30 minutes, then no step fires and the task shows "Suggested: P1 (91%)".

### ESC-AC19
Requirement: ESC-N01
Coverage: full
Criterion: Given a task suggested as P1, when a support agent selects Override and chooses P3, then the task's priority is P3, its activity records the agent and the time, and no P1 rule applies to it.

### ESC-AC21
Requirement: ESC-N03
Coverage: full
Criterion: Given an API request authenticated as a Member, when it asks to change a rule, then Relay returns HTTP 403 and the rule is unchanged.

### ESC-AC22
Requirement: ESC-N03
Coverage: full
Criterion: Given an Admin, when they change a step's delay from 10 to 15 minutes, then the audit log has one entry with the Admin, the time, and both delays.

### ESC-AC23
Requirement: ESC-N04
Coverage: full
Criterion: Given a target who has received 20 escalation emails in the past hour, when another step for that target fires, then Relay records it on the task, sends no email for it, and lists it in the summary email at the end of the hour.

### ESC-AC24
Requirement: ESC-N05
Coverage: full
Criterion: Given a rule, when an API request sets a target to an email address outside the workspace, then Relay refuses the request and the audit log records the refusal.

### ESC-AC26
Requirement: ESC-N06
Coverage: full
Criterion: Given a P1 rule, when an Admin removes its last target, then Relay refuses the change.

### ESC-AC27
Requirement: ESC-N07
Coverage: full
Criterion: Given a P1 task titled "Customer 4471 card data exposed", when a step fires, then neither the email nor the webhook payload contains the title or any part of it, and both contain the task's link.

### ESC-AC31
Requirement: ESC-N10
Coverage: full
Criterion: Given the version 1 configuration, when the services that escalation code calls are listed, then the list contains only Relay's email and webhook delivery.

## Change log

| Version | Date | Change | Approved by |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-24 | First approved version, from PRD v1.0 | lena.k, sam.o, aisha.r |
| 1.1.0 | 2026-11-30 | The engine, from PRD v1.1: business hours for P2 to P4 rules (D10, D11, ADR-010), storage and audit, the evaluation pass and outbox (ADR-011), delivery messages, priorities, suggestions and acknowledgement, the flood cap, HTTP routes and their OpenAPI contract (ADR-009); SEC-01, SEC-03, SEC-04 and SEC-05 widened, SEC-06 and SEC-07 added; 11 criteria added, and ESC-AC08, ESC-AC18, ESC-AC24 and ESC-AC27 now full. MINOR by caller compatibility | lena.k, sam.o, aisha.r |

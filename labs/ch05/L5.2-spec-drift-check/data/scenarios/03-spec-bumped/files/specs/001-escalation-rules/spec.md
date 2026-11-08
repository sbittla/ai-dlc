# Spec — Escalation rule evaluation

Spec: ESC-SPEC-1
Version: 1.1.0
Status: approved
Derived from: prd-v1.md@1.0
Risk: high
Product owner: lena.k
Tech lead: sam.o
Security reviewer: aisha.r
Approved by: lena.k, sam.o, aisha.r
Approved on: 2026-11-24
Relay release: 4.18.0

## Goals

- Decide, for any rule and task, exactly which steps fire and when, as PRD v1.0 specifies for P1 timed steps (PRD G1).
- Refuse every rule that PRD v1.0 forbids before it can be saved: wrong editor, delay out of range, steps out of order, missing or unreachable targets (PRD G1, G3).
- Keep task content out of everything the evaluator returns, because delivery sends it outside Relay (PRD G3).
- Give the later stages a versioned contract to build against: storage and delivery (Chapter 8) and the HTTP service (Chapter 6).

## Non-goals

- Storing rules or escalation state. Callers pass both in; Chapter 8 adds storage.
- Sending email or webhook events, and explaining escalations (ESC-R09 to ESC-R11). The evaluator decides; delivery is a later stage.
- Recording acknowledgement (ESC-R02). The evaluator reads `acknowledged_at`; it never sets it.
- Business hours for P2 rules (ESC-R07). Two PRD open questions, daylight-saving changes and weekends, are unresolved. Until Chapter 8 adds them, `validate_rule` refuses rules for any priority but P1.
- The flood cap (ESC-N04), the audit log (ESC-N03), calibration (ESC-N02), the rule editor's accessibility (ESC-N08) and operability measures (ESC-N09).
- An HTTP endpoint. Chapter 6 adds Relay's service; its handlers will call this slice and use this contract.

## Actors

| Actor | Relay role | In this slice |
| --- | --- | --- |
| Rule editor | Owner or Admin (D2) | Submits a rule to `validate_rule` |
| Other workspace users | Member or Guest | Refused as editors; may be targets if they can view the project |
| Target | Any workspace user who can view the rule's project (ESC-R08) | Named by user ID in a step |
| Evaluator caller | Relay code (later: Chapter 8's scheduler) | Calls `evaluate` with the rule, task, state and the current UTC time |
| Triage model | Not a user | Its suggested priority is stored in the state and never read by `evaluate` (D3) |

## Behavior

### B1 — Rule validation

Requirements: ESC-R03, ESC-R05, ESC-R08, ESC-N05, ESC-N06

`validate_rule(rule, editor, project, users)` returns the rule unchanged if Relay may save it, and raises `RuleRejected` otherwise. It is a pure function: it reads nothing but its arguments and changes nothing. Checks run in this order, and the first failure is raised:

1. The editor (`not_rule_editor`).
2. The priority (`unsupported_priority`).
3. At least one step (`no_steps`).
4. Each step in turn, all of step 1 before any of step 2: (a) its number (`steps_not_numbered`); (b) its delay's range (`delay_out_of_range`); (c) its delay against the previous step's (`delays_not_increasing`); (d) at least one target (`no_targets`); (e) each target in turn (`target_not_user`, `target_not_in_workspace`, `target_cannot_view_project`).

So a rule whose step 1 has no targets and whose step 2 has a 4-minute delay is refused with `no_targets`.

| Code | When | Criterion |
| --- | --- | --- |
| `not_rule_editor` | The editor is not an Owner or Admin (D2) | ESC-AC06 |
| `unsupported_priority` | The rule's priority is not P1; P2 rules need business hours (ESC-R07), which this release does not have | – |
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

`evaluate(rule, task, state, now)` decides which of the rule's steps fire for one task at `now`, an aware UTC time. A step is due at `priority_set_at` plus its delay, and fires when `now` is at or after its due time. Every due step that has not already fired is returned, in step order, so a late evaluation still fires each step once. A step never fires twice (D9).

| Status | When |
| --- | --- |
| `not_applicable` | The task has no priority set by a person, or its priority differs from the rule's. A suggested priority never counts (D3) |
| `acknowledged` | The task has been acknowledged; its remaining steps are cancelled (D9) |
| `active` | At least one step has not yet fired after this evaluation |
| `complete` | Every step has fired, now or earlier |

### Terms at this boundary

The PRD's criteria describe the whole feature. In this slice: a step **fires** when `evaluate` returns it in `fire`. A rule **saves** when `validate_rule` accepts it, and Relay **refuses** when `validate_rule` raises `RuleRejected`; because `validate_rule` is pure, a refused rule is **unchanged**. Notifying targets is delivery, which is not in this slice. Criteria that need more than these terms, such as a notification, a display or an audit entry, are marked `partial` below, with the deferred part named.

## Non-functional requirements

| Source | Requirement in this slice | How it is checked |
| --- | --- | --- |
| ESC-N01 | `evaluate` never reads the triage model's suggestion | ESC-AC18; policy test SEC-03 |
| ESC-N05 | Targets are workspace user IDs only | ESC-AC24; the contract's integer targets |
| ESC-N07 | Documents for delivery carry IDs, step numbers and times only | ESC-AC27; policy test SEC-04 |
| ESC-N10 | The slice calls no service: no network, file or subprocess access | Policy test SEC-05 |
| Slice | `validate_rule` and `evaluate` are deterministic: the current time is an argument, never read from a clock | Every acceptance test passes a fixed time |

## Contracts

Contract: contracts/escalation-rules.schema.json
Outbound: Evaluation, StepDecision

The contract is a JSON Schema (2020-12) with five definitions: `Rule` and `Step` (documents in), `Evaluation` and `StepDecision` (documents out, for delivery), and `Rejection` (refusals, shown to the editor inside Relay). Its `x-spec-version` must equal this spec's version. In this version `Rule.priority` allows only P1, matching B1; accepting P2 rules later widens it, a MINOR change. Relay validates documents with `relay.escalation.validate`, which implements only the keywords the contract uses and refuses any other.

## Data rules

Classes: Public; Internal (Relay staff and the workspace's own users); Confidential (customer content and personal data); Restricted (secrets and credentials).

| Field | Classification | Rule |
| --- | --- | --- |
| `Rule.rule_id` | Internal | – |
| `Rule.project_id` | Internal | – |
| `Rule.priority` | Internal | – |
| `Rule.steps` | Internal | – |
| `Step.number` | Internal | – |
| `Step.delay_minutes` | Internal | Whole minutes, 5 to 240 |
| `Step.targets` | Internal | User IDs only, never addresses (ESC-N05) |
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
| `Task.title` | Confidential | Never in a document for delivery (ESC-N07) |
| `User.name` | Confidential | Never in a document for delivery |
| `User.email` | Confidential | Never in a document for delivery; never a target (ESC-N05) |
| `EscalationState.suggested_priority` | Internal | Untrusted model output; never an input to evaluation (D3) |

## Security constraints

### SEC-01 — Only Owners and Admins change rules
Source: ESC-R03, ESC-N03, D2
Checks: ESC-AC06
Statement: `validate_rule` must refuse any editor who is not an Owner or Admin, whatever the caller's user interface allows. Chapter 6's service must call it on the server for every rule change.

### SEC-02 — Targets are reachable workspace users
Source: ESC-R08, ESC-N05, ESC-N06
Checks: ESC-AC13, ESC-AC14, ESC-AC24, ESC-AC26
Statement: Every step must have at least one target, and every target must be the integer ID of a workspace user who can view the rule's project. An email address, phone number or URL is refused.

### SEC-03 — A suggestion never starts an escalation
Source: ESC-N01, D3
Checks: ESC-AC18, test_SEC03
Statement: `evaluate` must read only the priority a person set. The triage model's suggestion is untrusted input, because a ticket's text can steer it, and the evaluator must not read it.

### SEC-04 — No task content in documents for delivery
Source: ESC-N07
Checks: ESC-AC27, test_SEC04
Statement: Every field of `Evaluation` and `StepDecision` must be classified Internal or Public in the data rules. Delivery builds email and webhook payloads from these documents, so task titles, descriptions, comments, names and addresses must not be in them.

### SEC-05 — The slice reaches nothing outside the process
Source: ESC-N10 (refined)
Checks: test_SEC05
Statement: This constraint refines ESC-N10, which forbids paid services, into a rule a test can check, and the refinement is approved here by the security reviewer. The escalation package must import only the standard-library modules its policy test allows, and must not open files, run code from strings or call services.

## Acceptance criteria

### ESC-AC02
Requirement: ESC-R01
Coverage: full
Criterion: Given a task with no priority and an active rule for its project, when 24 hours pass, then no step fires for the task.

### ESC-AC06
Requirement: ESC-R03
Coverage: full
Criterion: Given a Member, when they try to save a change to a rule, then Relay refuses the change and the rule is unchanged.

### ESC-AC08
Requirement: ESC-R04
Coverage: partial
Criterion: Given an active P1 rule with steps at 10 and 20 minutes, when a P1 task stays unacknowledged for 10 minutes, then the first step's targets are notified and the second step's targets are not.
Deferred: delivering the notification to the targets (ESC-R09, Chapter 8)

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

### ESC-AC13
Requirement: ESC-R08
Coverage: full
Criterion: Given a Guest invited to the Rotterdam project, when an Admin adds the Guest as a target of that project's P1 rule, then the rule saves.

### ESC-AC14
Requirement: ESC-R08
Coverage: full
Criterion: Given a Guest not invited to the Rotterdam project, when an Admin adds the Guest as a target of that project's rule, then Relay refuses the change and names the Guest.

### ESC-AC18
Requirement: ESC-N01
Coverage: partial
Criterion: Given a task the triage model suggests as P1 with 91% confidence, when nobody confirms it for 30 minutes, then no step fires and the task shows "Suggested: P1 (91%)".
Deferred: the task showing "Suggested: P1 (91%)" (the task view, Chapter 8)

### ESC-AC24
Requirement: ESC-N05
Coverage: partial
Criterion: Given a rule, when an API request sets a target to an email address outside the workspace, then Relay refuses the request and the audit log records the refusal.
Deferred: the audit log entry for the refusal (ESC-N03, Chapter 8); the API request itself (Chapter 6)

### ESC-AC26
Requirement: ESC-N06
Coverage: full
Criterion: Given a P1 rule, when an Admin removes its last target, then Relay refuses the change.

### ESC-AC27
Requirement: ESC-N07
Coverage: partial
Criterion: Given a P1 task titled "Customer 4471 card data exposed", when a step fires, then neither the email nor the webhook payload contains the title or any part of it, and both contain the task's link.
Deferred: the email and webhook payloads, and the task's link in them (ESC-R09, Chapter 8); this slice checks the evaluation document they are built from

### ESC-AC12
Requirement: ESC-R07
Coverage: full
Criterion: Given a P2 rule with business hours 06:00 to 22:00 in Europe/Berlin and one step at 4 business hours, when a task's priority is set to P2 at 21:00 local time and it stays unacknowledged, then the step fires at 09:00 local time the next day.

## Change log

| Version | Date | Change | Approved by |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-24 | First approved version, from PRD v1.0 | lena.k, sam.o, aisha.r |

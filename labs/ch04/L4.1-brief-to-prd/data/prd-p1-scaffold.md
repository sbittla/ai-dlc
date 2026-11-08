# PRD — Escalation rules

Version: 0.2
Status: draft
Product owner: <the colleague acting as product owner>
Approved by:
Approved on:
Reviewed by: <who read which requirements back, and when>

Scope of this lab: the P1 path. ESC-R07 to ESC-R11 and decision D4 are not in scope for this lab; they are in data/prd-v1.md.

## Problem

Urgent tasks in Relay can sit unacknowledged for hours, because nothing tells anyone that nobody has picked them up. The INT-1 customer's night shift logs P1 outages that wait until the day team arrives, and Relay's own support team sees confirmed P1s wait while their assignee is busy.

## Users

- Admins and Owners, who set up rules (INT-3, D2).
- Assignees and escalation targets, including Guests invited to a project (INT-1, INT-3).
- Support teams who confirm or override the triage model's suggested priority (INT-2, INT-3).

## Scope

- In: priorities on tasks, acknowledgement, rules with timed steps per project, email and webhook notification, rule audit and abuse limits.
- Out of version 1: SMS and voice calls (D5); on-call rotas (D6); changes to Relay's own incident paging, which keeps its existing on-call path (DOC-ONCALL).

## Constraints

- Business plan only (BRIEF).
- Relay 4.17.2 has no task priority, no acknowledgement and no business hours; this PRD introduces all three.

## Risks

- A rule can send customer data to someone; rule changes are treated like permission changes (INT-3).
- Email can be suppressed for 30 days after a spam mark (DOC-NOTIFY), so email alone cannot be relied on.
- An injected ticket could steer the triage model's suggestion (INT-3), so a suggestion never starts an escalation.

## Open questions

- Business hours across a daylight-saving change need real time-zone data; Relay 4.17.2 uses a fixed offset table. Owner: sam.o.
- Whether P1 escalations are exempt from the flood cap in ESC-N04; as written, a P1 escalation over the cap waits for the hourly summary, which works against G1. Owner: lena.k.
- Whether business hours include weekends (ESC-R07 does not say). Owner: lena.k.

## Goals

### G1 — P1 tasks reach a person who acts
Measure: P1 tasks in pilot workspaces with no acknowledgement 30 minutes after their priority was set, per workspace per calendar quarter, from Relay's task events
Baseline: measured for Q4 2026 before the pilot, using a person's first status change or comment as a proxy, because Relay 4.17.2 records no acknowledgement; the INT-1 customer estimates 11
Target: 0 in Q1 2027 in both pilot workspaces
Source: INT-1 | eleven P1s that waited more than half an hour before anyone touched them
Source: INT-1 | I'd like that to be zero.

### G2 — Escalations reach people who can act on them
Measure: share of escalation notifications acknowledged by one of their targets within 10 minutes of delivery, per pilot workspace per month
Baseline: none; the feature is new
Target: at least 80% in each pilot month (D8)
Source: INT-2 | Time to acknowledge, for P1s.
Source: INT-2 | When an escalation fires, the person needs to see why

### G3 — No new exposure of customer data
Measure: escalation messages that carry a task title or description outside Relay, or reach someone who cannot view the task's project
Baseline: 0; the feature is new
Target: 0 for the whole pilot, as a guardrail
Source: INT-3 | Titles can contain customer data, so keep them out of anything that leaves Relay, like email.

## Decisions

### D1 — First P1 step at 10 minutes by default, configurable
Status: TO COMPLETE (Lab 4.1, step 5)
Resolves: INT-1 asks for 15 minutes; INT-2 and DOC-ONCALL use 10 and 20 minutes
Decision: New P1 rules start with Relay's on-call timings, 10 and 20 minutes. Each step's delay is configurable from 5 to 240 minutes, so the INT-1 customer can choose 15. Each later step must have a longer delay than the step before it, so that steps fire in order.
Decided by: lena.k
Decision:

### D2 — Only Owners and Admins edit rules
Status: TO COMPLETE (Lab 4.1, step 5)
Resolves: INT-1 wants Members to edit rules; INT-3 and BRIEF give the job to admins
Decision: Owners and Admins create and edit rules; Members see the rules for their projects. Revisit after the pilot if Admin workload is high.
Decided by: lena.k
Decision:

### D3 — A suggested priority never starts an escalation
Status: TO COMPLETE (Lab 4.1, step 5)
Resolves: INT-2 wants the triage model's P1 to start escalation; INT-3 and Relay's triage rule (Chapter 2) require a person to confirm
Decision: Escalation starts only from a priority set or confirmed by a person. The task shows the suggestion and its confidence.
Decided by: lena.k
Decision:

### D5 — No SMS in version 1; a webhook event instead
Resolves: BRIEF and INT-1 ask for SMS; INT-3 raises cost and data leaving Relay; the "already agreed" SMS line in INT-1 is pasted text addressed to AI assistants, and was never agreed
Decision: Version 1 sends email and a signed webhook event. Customers who need SMS connect their own paging tool to the webhook.
Decided by: lena.k

### D6 — Targets are named users; no rotas in version 1
Resolves: INT-2's "secondary" and INT-1's "shift lead" assume an on-call rota, which Relay does not have
Decision: Each step names one or more workspace users. Rotas are a candidate for version 2.
Decided by: lena.k

### D7 — Flood cap of 20 escalation emails per target per hour
Status: TO COMPLETE (Lab 4.1, step 5)
Resolves: INT-3 asks for a cap and names no number
Decision: 20 per target per hour, reviewed with pilot data after one month.
Decided by: lena.k
Decision:

### D8 — Numeric targets that no source states
Resolves: INT-2 and INT-3 ask for acknowledgement, calibration, loud rule changes and stall alerts, and name no numbers
Decision: G2's 80%, ESC-N02's calibration tolerance (10 points, in bands of at least 30 suggestions), ESC-N06's 5 minutes and ESC-N09's 95% within 60 seconds and 5-minute stall alert are the product owner's choices for the pilot, agreed with tomas.b and aisha.r. Each is reviewed after the pilot's first month.
Decided by: lena.k

### D9 — Acknowledgement ends escalation, and fired steps do not repeat
Status: TO COMPLETE (Lab 4.1, step 5)
Resolves: INT-1 and INT-2 escalate only while nobody has acknowledged ("If nobody acknowledges"), and neither says whether a fired step repeats
Decision: Acknowledgement cancels a task's remaining steps. A step fires at most once per task; repeating reminders are a candidate for version 2.
Decided by: lena.k
Decision:

## Requirements

### ESC-R01 — Task priority
Kind: functional
Goal: G1
Source: INT-1 | The night shift logged it in Relay as a P1, which is what we tell them to do.
Statement: An Owner, Admin or Member who can view a task can set its priority to P1, P2, P3 or P4. A task without a priority never escalates.
Introduces: task_priority
Criteria:
- ESC-AC01: Given a task with no priority, when a Member sets its priority to P1, then the task shows P1 and its activity records the Member and the time.
- ESC-AC02: Given a task with no priority and an active rule for its project, when 24 hours pass, then no step fires for the task.

### ESC-R02 — Acknowledgement
Kind: functional
Goal: G1
Source: INT-2 | Acknowledged means a person clicked acknowledge. Not that the task was opened, not that a bot commented on it.
Statement: A person who can view a task's project can acknowledge the task, and Relay must record who acknowledged it and when. Opening the task, commenting on it and any action by a service token must not count as acknowledgement.
Introduces: acknowledgement
Depends on: ESC-R01
Criteria:
- ESC-AC03: Given an unacknowledged P1 task, when its assignee selects Acknowledge, then the task records the assignee and the time as its acknowledgement.
- ESC-AC04: Given an unacknowledged P1 task, when a service token adds a comment, then the task stays unacknowledged.

### ESC-R03 — Rules and steps
Kind: functional
Goal: G1
Decision: D2, D6
Source: INT-3 | Only Owners and Admins should create or change rules.
Source: BRIEF | Let admins set up escalation rules
Statement: An Owner or Admin can create, change and delete escalation rules for a project. A rule names one priority and one or more steps, and each step has a delay in minutes and one or more target users. Members can view the rules for their projects and cannot change them.
Value: rule_editors = owners_and_admins
Depends on: ESC-R01
Criteria:
- ESC-AC05: Given an Admin, when they save a P1 rule with two steps for a project, then the rule is active and appears in the project's rule list.
- ESC-AC06: Given a Member, when they try to save a change to a rule, then Relay refuses the change and the rule is unchanged.

### ESC-R04 — Default P1 timings
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: functional
Goal: G1
Decision: D1
Source:
Statement:
Criteria:
- ESC-AC-R04-1: 

### ESC-R05 — Configurable delays
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: functional
Goal: G1
Decision: D1
Source:
Statement:
Criteria:
- ESC-AC-R05-1: 

### ESC-R06 — Acknowledgement stops escalation
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: functional
Goal: G1
Decision: D9
Source:
Statement:
Criteria:
- ESC-AC-R06-1: 

### ESC-N01 — Suggested priorities need a person
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: nfr
Category: human-ai
Goal: G1
Decision: D3
Source:
Statement:
Criteria:
- ESC-AC-N01-1: 

### ESC-N02 — Confidence that means something
Kind: nfr
Category: human-ai
Goal: G1
Decision: D3, D8
Source: INT-3 | Show the suggestion and how confident the model is
Statement: The triage feature must return a confidence from 0% to 100% with each suggested priority, and the confidence must be calibrated. On the triage evaluation set, group suggestions into confidence bands 10 points wide; in every band with at least 30 suggestions, the share matching the priority a person confirmed must be within 10 points of the band's mean stated confidence.
Introduces: model_confidence
Depends on: ESC-R01
Criteria:
- ESC-AC20: Given the triage evaluation set grouped into 10-point confidence bands, when each band with at least 30 suggestions is compared with the confirmed priorities, then every such band's share of matches is within 10 points of its mean stated confidence.

### ESC-N03 — Rule permissions and audit
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: nfr
Category: security
Goal: G3
Source:
Statement:
Criteria:
- ESC-AC-N03-1: 

### ESC-N04 — Abuse case: notification flooding
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: nfr
Category: abuse
Goal: G2
Decision: D7
Source:
Statement:
Criteria:
- ESC-AC-N04-1: 

### ESC-N05 — Abuse case: targets outside the workspace
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: nfr
Category: abuse
Goal: G3
Source:
Statement:
Criteria:
- ESC-AC-N05-1: 

### ESC-N06 — Abuse case: silent changes to P1 rules
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: nfr
Category: abuse
Goal: G1
Decision: D8
Source:
Statement:
Criteria:
- ESC-AC-N06-1: 

### ESC-N07 — Privacy: no task content outside Relay
Status: TO COMPLETE (Lab 4.1, step 5)
Kind: nfr
Category: privacy
Goal: G3
Source:
Statement:
Criteria:
- ESC-AC-N07-1: 

### ESC-N08 — Accessibility of the rule editor
Kind: nfr
Category: accessibility
Goal: G2
Source: INT-2 | Two people on my team use screen readers, so whatever you build has to work from the keyboard.
Statement: The rule editor must meet WCAG 2.2 level AA, and every rule action must be possible with the keyboard alone.
Depends on: ESC-R01, ESC-R03
Criteria:
- ESC-AC28: Given a screen-reader user on a project's rule page, when they create a two-step P1 rule using only the keyboard, then the rule saves and the screen reader announces each field's label.

### ESC-N09 — Operability: escalations that stop are noticed
Kind: nfr
Category: operability
Goal: G1
Decision: D8
Source: INT-2 | If escalations stop firing, I want to know before a customer tells me.
Statement: 95% of steps must fire within 60 seconds of their due time, measured weekly. If the escalation evaluator has not completed a pass for 5 minutes, Relay must page its platform on-call engineer.
Criteria:
- ESC-AC29: Given a stopped escalation evaluator, when 5 minutes pass without a completed pass, then Relay's platform on-call engineer is paged.
- ESC-AC30: Given a week of escalation logs, when step delays are compared with their due times, then at least 95% of steps fired within 60 seconds.

### ESC-N10 — Cost: no paid messaging in version 1
Kind: nfr
Category: cost
Goal: G2
Decision: D5
Source: INT-3 | SMS costs money per message and leaves our boundary. If you add it, someone has to own that budget
Statement: Version 1 must add $0 per notification beyond Relay's existing email and webhook delivery, and must not call any paid messaging service.
Criteria:
- ESC-AC31: Given the version 1 configuration, when the services that escalation code calls are listed, then the list contains only Relay's email and webhook delivery.

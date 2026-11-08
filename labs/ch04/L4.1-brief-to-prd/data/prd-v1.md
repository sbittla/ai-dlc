# PRD — Escalation rules

Version: 1.0
Status: approved
Product owner: lena.k
Approved by: lena.k
Approved on: 2026-11-19
Reviewed by: tomas.b (support), aisha.r (security), sam.o (engineering)

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
Resolves: INT-1 asks for 15 minutes; INT-2 and DOC-ONCALL use 10 and 20 minutes
Decision: New P1 rules start with Relay's on-call timings, 10 and 20 minutes. Each step's delay is configurable from 5 to 240 minutes, so the INT-1 customer can choose 15. Each later step must have a longer delay than the step before it, so that steps fire in order.
Decided by: lena.k

### D2 — Only Owners and Admins edit rules
Resolves: INT-1 wants Members to edit rules; INT-3 and BRIEF give the job to admins
Decision: Owners and Admins create and edit rules; Members see the rules for their projects. Revisit after the pilot if Admin workload is high.
Decided by: lena.k

### D3 — A suggested priority never starts an escalation
Resolves: INT-2 wants the triage model's P1 to start escalation; INT-3 and Relay's triage rule (Chapter 2) require a person to confirm
Decision: Escalation starts only from a priority set or confirmed by a person. The task shows the suggestion and its confidence.
Decided by: lena.k

### D4 — Business hours belong to the rule
Resolves: whose clock counts for "four business hours" (INT-1: each warehouse's local time; INT-2: not stated)
Decision: Each rule carries its own business hours and time zone; viewers' time zones do not change when a step fires.
Decided by: lena.k

### D5 — No SMS in version 1; a webhook event instead
Resolves: BRIEF and INT-1 ask for SMS; INT-3 raises cost and data leaving Relay; the "already agreed" SMS line in INT-1 is pasted text addressed to AI assistants, and was never agreed
Decision: Version 1 sends email and a signed webhook event. Customers who need SMS connect their own paging tool to the webhook.
Decided by: lena.k

### D6 — Targets are named users; no rotas in version 1
Resolves: INT-2's "secondary" and INT-1's "shift lead" assume an on-call rota, which Relay does not have
Decision: Each step names one or more workspace users. Rotas are a candidate for version 2.
Decided by: lena.k

### D7 — Flood cap of 20 escalation emails per target per hour
Resolves: INT-3 asks for a cap and names no number
Decision: 20 per target per hour, reviewed with pilot data after one month.
Decided by: lena.k

### D8 — Numeric targets that no source states
Resolves: INT-2 and INT-3 ask for acknowledgement, calibration, loud rule changes and stall alerts, and name no numbers
Decision: G2's 80%, ESC-N02's calibration tolerance (10 points, in bands of at least 30 suggestions), ESC-N06's 5 minutes and ESC-N09's 95% within 60 seconds and 5-minute stall alert are the product owner's choices for the pilot, agreed with tomas.b and aisha.r. Each is reviewed after the pilot's first month.
Decided by: lena.k

### D9 — Acknowledgement ends escalation, and fired steps do not repeat
Resolves: INT-1 and INT-2 escalate only while nobody has acknowledged ("If nobody acknowledges"), and neither says whether a fired step repeats
Decision: Acknowledgement cancels a task's remaining steps. A step fires at most once per task; repeating reminders are a candidate for version 2.
Decided by: lena.k

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
Kind: functional
Goal: G1
Decision: D1
Source: INT-2 | If nobody acknowledges a P1 within ten minutes, the secondary gets paged. At twenty minutes it goes to the engineering manager.
Source: DOC-ONCALL | If the page is not acknowledged within 10 minutes, it escalates to the secondary on-call, and after 20 minutes to the engineering manager.
Statement: A new P1 rule must start with two steps, at 10 and 20 minutes after the task's priority is set to P1. The Admin chooses each step's targets.
Value: p1_default_step_minutes = 10, 20
Depends on: ESC-R01, ESC-R02, ESC-R03
Criteria:
- ESC-AC07: Given an Admin creating a P1 rule, when the rule form opens, then it shows two steps with delays of 10 and 20 minutes.
- ESC-AC08: Given an active P1 rule with steps at 10 and 20 minutes, when a P1 task stays unacknowledged for 10 minutes, then the first step's targets are notified and the second step's targets are not.

### ESC-R05 — Configurable delays
Kind: functional
Goal: G1
Decision: D1
Source: INT-1 | If a P1 sits for fifteen minutes with nobody on it, it should go to the shift lead.
Statement: An Admin can set each step's delay to a whole number of minutes from 5 to 240. Relay must refuse a delay outside that range, and each step's delay must be greater than the delay of the step before it.
Value: step_delay_minutes_range = 5-240
Depends on: ESC-R01, ESC-R03
Criteria:
- ESC-AC09: Given a P1 rule, when an Admin sets the first step's delay to 15 minutes, then the rule saves and the first step fires 15 minutes after a task's priority is set to P1.
- ESC-AC10: Given a P1 rule, when an Admin sets a step's delay to 4 minutes, then Relay refuses the change with a message that names the allowed range.

### ESC-R06 — Acknowledgement stops escalation
Kind: functional
Goal: G1
Decision: D9
Source: INT-2 | If nobody acknowledges a P1 within ten minutes, the secondary gets paged.
Source: INT-1 | If a P1 sits for fifteen minutes with nobody on it
Statement: When a task is acknowledged, Relay must cancel its remaining steps. A step that has already fired is not repeated.
Depends on: ESC-R01, ESC-R02, ESC-R03
Criteria:
- ESC-AC11: Given a P1 task whose first step has fired, when a target acknowledges the task, then the second step does not fire.

### ESC-R07 — P2 rules count business hours
Kind: functional
Goal: G1
Decision: D4
Source: INT-2 | P2s just need an acknowledgement within four business hours, same as the incident policy.
Source: INT-1 | Six in the morning to ten at night, local time.
Statement: A P2 rule counts only its own business hours, given as a daily start time, an end time and a time-zone name. A new P2 rule starts with one step at 4 business hours.
Value: p2_default_step_business_hours = 4
Introduces: business_hours
Depends on: ESC-R01, ESC-R02, ESC-R03
Criteria:
- ESC-AC12: Given a P2 rule with business hours 06:00 to 22:00 in Europe/Berlin and one step at 4 business hours, when a task's priority is set to P2 at 21:00 local time and it stays unacknowledged, then the step fires at 09:00 local time the next day.

### ESC-R08 — Targets can see the project
Kind: functional
Goal: G3
Source: INT-3 | Never send an escalation to someone who can't see the project.
Source: INT-3 | Guests are fine for projects they're invited to, and nowhere else.
Source: INT-1 | At night our shift leads are contractors, so in Relay they're Guests.
Statement: A step's targets must be workspace users who can view the rule's project. A Guest can be a target only in a project the Guest is invited to, and Relay must refuse to save a rule with any other target.
Depends on: ESC-R01, ESC-R03
Criteria:
- ESC-AC13: Given a Guest invited to the Rotterdam project, when an Admin adds the Guest as a target of that project's P1 rule, then the rule saves.
- ESC-AC14: Given a Guest not invited to the Rotterdam project, when an Admin adds the Guest as a target of that project's rule, then Relay refuses the change and names the Guest.

### ESC-R09 — Email and webhook notification
Kind: functional
Goal: G2
Decision: D5
Source: INT-2 | Not email alone. Email is not reliable for this.
Source: DOC-WEBHOOKS | Workflow webhooks are delivered with an HMAC-SHA256 signature in the X-Relay-Signature header.
Statement: When a step fires, Relay must email each of its targets and emit one task.escalated webhook event, signed like every other Relay webhook.
Depends on: ESC-R03
Criteria:
- ESC-AC15: Given a workspace with one webhook and a step with two targets, when the step fires, then Relay sends two emails and one task.escalated event with an X-Relay-Signature header.

### ESC-R10 — Suppressed email addresses
Kind: functional
Goal: G2
Source: INT-2 | Relay stopped emailing that address for thirty days. Nobody noticed until they complained.
Source: DOC-NOTIFY | Relay then suppresses further emails to that address for 30 days to protect its sending reputation.
Statement: If a target's email address is suppressed, Relay must record on the task that the escalation was not emailed, and show a warning naming the target on the rule's page to every Admin.
Depends on: ESC-R03, ESC-R09
Criteria:
- ESC-AC16: Given a target whose email address is suppressed, when a step for that target fires, then the task's activity shows the escalation as not emailed and the rule's page shows a warning naming the target.

### ESC-R11 — Every escalation explains itself
Kind: functional
Goal: G2
Source: INT-2 | When an escalation fires, the person needs to see why: which rule fired, which step, and when the clock started.
Statement: Every escalation email, webhook event and task activity entry must show the rule's name, the step number, the time the step's delay started and the time the step fired, in UTC.
Depends on: ESC-R03, ESC-R09
Criteria:
- ESC-AC17: Given a step whose delay started at 02:30 UTC and that fires at 02:40 UTC, when the target opens the escalation email, then it shows the rule's name, step 1, 02:30 UTC and 02:40 UTC.

### ESC-N01 — Suggested priorities need a person
Kind: nfr
Category: human-ai
Goal: G1
Decision: D3
Source: INT-3 | The AI priority is a suggestion. A person confirms a P1 before anything pages anyone.
Source: INT-3 | Show the suggestion and how confident the model is, by all means, and let people override it.
Source: INT-2 | If the model says P1, escalate straight away.
Statement: A priority suggested by the triage model must not start an escalation. The task must show the suggestion, its confidence as a percentage, and Confirm and Override actions; only a person's confirmation or override sets the priority, and Relay must record who did it.
Value: ai_p1_starts_escalation = no
Depends on: ESC-R01, ESC-N02
Criteria:
- ESC-AC18: Given a task the triage model suggests as P1 with 91% confidence, when nobody confirms it for 30 minutes, then no step fires and the task shows "Suggested: P1 (91%)".
- ESC-AC19: Given a task suggested as P1, when a support agent selects Override and chooses P3, then the task's priority is P3, its activity records the agent and the time, and no P1 rule applies to it.

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
Kind: nfr
Category: security
Goal: G3
Source: INT-3 | Every rule change goes in the audit log, with who changed it, when, and what it was before.
Source: DOC-RETENTION | Audit log entries are retained for 400 days on the Business plan and 90 days on the Team plan.
Statement: Relay must enforce rule permissions on the server as well as in the editor. It must write an audit log entry for every rule creation, change and deletion, with the user, the time and the rule before and after, kept for 400 days.
Depends on: ESC-R03
Criteria:
- ESC-AC21: Given an API request authenticated as a Member, when it asks to change a rule, then Relay returns HTTP 403 and the rule is unchanged.
- ESC-AC22: Given an Admin, when they change a step's delay from 10 to 15 minutes, then the audit log has one entry with the Admin, the time, and both delays.

### ESC-N04 — Abuse case: notification flooding
Kind: nfr
Category: abuse
Goal: G2
Decision: D7
Source: INT-3 | Someone will use a rule to flood a colleague with notifications. Cap it.
Statement: Relay must send at most 20 escalation emails per target per hour across all rules. Further escalations for that target in the hour must appear in the task's activity and in one summary email when the hour ends.
Value: max_escalation_emails_per_target_per_hour = 20
Depends on: ESC-R09
Criteria:
- ESC-AC23: Given a target who has received 20 escalation emails in the past hour, when another step for that target fires, then Relay records it on the task, sends no email for it, and lists it in the summary email at the end of the hour.

### ESC-N05 — Abuse case: targets outside the workspace
Kind: nfr
Category: abuse
Goal: G3
Source: INT-3 | Someone will try to escalate to an address outside the workspace.
Source: INT-3 | And no addresses outside the workspace, ever.
Statement: A step's target must be the ID of a user in the workspace. Relay must not accept an email address, a phone number or a URL as a target.
Depends on: ESC-R03
Criteria:
- ESC-AC24: Given a rule, when an API request sets a target to an email address outside the workspace, then Relay refuses the request and the audit log records the refusal.

### ESC-N06 — Abuse case: silent changes to P1 rules
Kind: nfr
Category: abuse
Goal: G1
Decision: D8
Source: INT-3 | a compromised account could change a rule quietly so that P1s go nowhere. Changing a P1 rule should be loud.
Statement: Relay must email the Owner and every Admin within 5 minutes when a P1 rule is changed or deleted. A P1 rule must not be saved with zero targets.
Depends on: ESC-R01, ESC-R03
Criteria:
- ESC-AC25: Given a workspace with one Owner and two Admins, when one Admin deletes a P1 rule, then the Owner and both Admins receive an email naming the rule and the Admin within 5 minutes.
- ESC-AC26: Given a P1 rule, when an Admin removes its last target, then Relay refuses the change.

### ESC-N07 — Privacy: no task content outside Relay
Kind: nfr
Category: privacy
Goal: G3
Source: INT-3 | Titles can contain customer data, so keep them out of anything that leaves Relay, like email. A link is enough.
Statement: Escalation emails and webhook events must not contain the task's title, description or comments. They must contain the task's link, its priority, the project's name, the rule's name and the step number.
Depends on: ESC-R01, ESC-R09, ESC-R11
Criteria:
- ESC-AC27: Given a P1 task titled "Customer 4471 card data exposed", when a step fires, then neither the email nor the webhook payload contains the title or any part of it, and both contain the task's link.

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
Depends on: ESC-R09
Criteria:
- ESC-AC31: Given the version 1 configuration, when the services that escalation code calls are listed, then the list contains only Relay's email and webhook delivery.

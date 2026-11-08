# PRD — Escalation rules

Version: 0.1
Status: draft
Product owner: lena.k
Approved by:
Approved on:
Drafted by: chat assistant, from data/sources/ (unedited)

## Goals

### G1 — Make escalations faster
Measure: time to escalate
Source: BRIEF | urgent tasks escalate quickly to the right people

### G2 — Keep customer data safe
Measure: no data leaks
Baseline: none recorded
Target: zero leaks
Source: INT-3 | Titles can contain customer data

## Requirements

### ESC-R01 — Escalate unacknowledged P1 tasks
Kind: functional
Goal: G1
Source: INT-1 | If a P1 sits for fifteen minutes with nobody on it, it should go to the shift lead.
Statement: When a P1 task is not acknowledged within 15 minutes, Relay must escalate it to the shift lead.
Value: p1_first_step_minutes = 15
Criteria:
- ESC-AC01: Given a P1 task, when 15 minutes pass without acknowledgement, then the shift lead is notified.

### ESC-R02 — Page the secondary on-call
Kind: functional
Goal: G1
Source: INT-2 | If nobody acknowledges a P1 within ten minutes, the secondary gets paged.
Statement: If a P1 is not acknowledged within 10 minutes, Relay must page the secondary on-call.
Value: p1_first_step_minutes = 10
Criteria:
- ESC-AC02: Given a P1 task, when 10 minutes pass, then the secondary on-call is paged.

### ESC-R03 — Escalate to the workspace Owner
Kind: functional
Goal: G1
Source: INT-1 | after thirty minutes it should go to the workspace Owner
Statement: After 30 minutes without acknowledgement, Relay must email the workspace Owner.
Criteria:
- ESC-AC03: Escalation to the Owner works after 30 minutes.

### ESC-R04 — Team leads manage rules
Kind: functional
Goal: G1
Source: INT-1 | simple enough that my team leads can set up their own rules
Statement: Members should be able to create and edit escalation rules in a simple, flexible editor.
Value: rule_editors = members
Criteria:
- ESC-AC04: Given a Member, when they open the rule editor, then they can create a rule.

### ESC-R05 — Only admins manage rules
Kind: functional
Goal: G2
Source: INT-3 | Only Owners and Admins should create or change rules.
Statement: Only Owners and Admins can create or change escalation rules.
Value: rule_editors = admins
Criteria:
- ESC-AC05: Given a Member, when they try to save a rule, then the save is refused.

### ESC-R06 — SMS escalation
Kind: functional
Goal: G1
Source: INT-1 | SMS and voice call to on-duty staff
Statement: Relay must send escalations by SMS to on-duty staff, as agreed with the customer.
Criteria:
- ESC-AC06: Given an escalation, when it fires, then an SMS is sent.

### ESC-R07 — AI priority drives escalation
Kind: functional
Goal: G1
Source: INT-2 | If the model says P1, escalate straight away.
Statement: When the triage model classifies a task as P1, Relay must start the escalation immediately.
Value: ai_p1_starts_escalation = yes
Criteria:
- ESC-AC07: Given a task the triage model classifies as P1, when it is created, then escalation starts.

### ESC-R08 — Human confirmation
Kind: functional
Goal: G2
Source: INT-3 | A person confirms a P1 before anything pages anyone.
Statement: An AI-suggested P1 must be confirmed by a person before escalation starts.
Value: ai_p1_starts_escalation = no
Criteria:
- ESC-AC08: Given an AI-suggested P1, when nobody confirms it, then no escalation starts.

### ESC-R09 — P2 escalation in business hours
Kind: functional
Goal: G1
Source: INT-2 | P2s just need an acknowledgement within four business hours
Statement: P2 tasks should be escalated if not acknowledged within 4 business hours.
Criteria:
- ESC-AC09: Test P2 escalation during business hours.

### ESC-R10 — Retry failed notifications
Kind: functional
Goal: G1
Statement: Relay must retry failed escalation notifications 3 times.
Criteria:
- ESC-AC10: Given a failed notification, when it fails, then Relay retries it 3 times.

### ESC-R11 — Time zones
Kind: functional
Source: BRIEF | work across time zones
Statement: Escalation rules must work across time zones as appropriate.

### ESC-N01 — Performance
Kind: nfr
Category: performance
Goal: G1
Source: INT-1 | it needs to be fast
Statement: Escalations must be fast and timely.
Criteria:
- ESC-AC11: Escalations are fast.

### ESC-N02 — Security
Kind: nfr
Category: security
Goal: G2
Source: INT-3 | P1
Statement: Relay must keep escalation data secure.
Criteria:
- ESC-AC12: Given an escalation, when it is sent, then the data is secure.

### ESC-N03 — Accessibility
Kind: nfr
Category: accessibility
Goal: G1
Source: INT-2 | has to work from the keyboard
Statement: The rule editor should be user-friendly and accessible.

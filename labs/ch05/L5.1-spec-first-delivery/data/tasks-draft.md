# Tasks — Escalation rule evaluation

Spec: ESC-SPEC-1@0.9.0
Planned by: coding assistant (draft, unedited)

### T01 — Escalation types
Checks: ESC-AC27
Depends on: –
Files: src/relay/escalation/model.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: New module.

### T02 — Rule validation and evaluation
Checks: ESC-AC02, ESC-AC06, ESC-AC08, ESC-AC09, ESC-AC10, ESC-AC11
Depends on: T01
Files: src/relay/escalation/rules.py, src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Core logic.

### T03 — Business-hours steps
Checks: ESC-AC12
Depends on: T02
Files: src/relay/escalation/hours.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: P2 rules need business hours.

### T04 — Target validation
Checks: ESC-AC13, ESC-AC14, ESC-AC26, SEC-01, SEC-02
Depends on: T02
Files: src/relay/escalation/rules.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T4
Why: Fully covered by tests, so the agent can merge when they pass.

### T05 — Suggested priorities
Checks: ESC-AC18, SEC-03
Depends on: T02
Files: src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py
Risk: high
Sensitive: yes
Untrusted input: yes
Tier: T3
Why: Uses the injection ticket TK32 as a fixture.

### T06 — SMS fallback channel
Checks: –
Depends on: T02
Files: src/relay/escalation/sms.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: INT-1 says SMS was agreed with the vendor.

### T07 — Privacy of evaluation documents
Checks: ESC-AC27, SEC-04
Depends on: T02, T11
Files: tests/escalation/test_escalation_policy.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier:
Why: Privacy guardrail.

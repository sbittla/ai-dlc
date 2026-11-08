# Tasks — Escalation rules engine

Spec: ESC-SPEC-1@1.1.0
Planned by: sam.o
Reviewed by: aisha.r (T04, T05, T08, T09, T11, T13, T14, T17, T19)

Each task is one pull request. Checks lists the criteria and security constraints the task's tests cover. Tiers follow Chapter 1, Table 1.6: a task whose agent reads untrusted input is capped at T2, and a sensitive task never runs at T4. Sensitive means irreversible or sensitive in Chapter 1's sense (data deletion, customer messages, money, secrets, personal data or security controls).

Tasks T01 to T09 were delivered in 4.18.0 (spec 1.0.0) and are kept so that every criterion has a task. Tasks T10 to T20 are test-first (test-strategy.md): a person writes or approves the task's tests, sees them fail for the right reason, and only then may an agent write the code. A task's tests are reviewed in their own commit, before the code's.

### T01 — Slice types, statuses and error codes
Checks: ESC-AC27
Depends on: –
Files: src/relay/escalation/__init__.py, src/relay/escalation/model.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Reversible by revert and checked by the contract tests; the fields chosen here decide what can leave the evaluator, so review compares them with the data rules.

### T02 — Contract validator and contract tests
Checks: ESC-AC24, ESC-AC27
Depends on: T01
Files: src/relay/escalation/contract.py, tests/escalation/test_escalation_contract.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Contained to one module; the validator must refuse keywords it does not implement, which a test checks.

### T03 — Delay and step validation
Checks: ESC-AC09, ESC-AC10
Depends on: T01
Files: src/relay/escalation/rules.py, tests/escalation/test_escalation_acceptance.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Pure function with boundary tests at 4, 5, 240 and 241 minutes.

### T04 — Editor and target visibility
Checks: ESC-AC06, ESC-AC13, ESC-AC14, SEC-01
Depends on: T03
Files: src/relay/escalation/rules.py, tests/escalation/test_escalation_acceptance.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: A permission check; reversible and fully tested, but a mistake sends customer data to the wrong people, so the security reviewer reviews it.

### T05 — Address targets and empty steps
Checks: ESC-AC24, ESC-AC26, SEC-02
Depends on: T04
Files: src/relay/escalation/rules.py, tests/escalation/test_escalation_acceptance.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: Abuse cases ESC-N05 and ESC-N06; same file and reviewer as T04.

### T06 — Timed steps
Checks: ESC-AC08, ESC-AC09
Depends on: T01
Files: src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Pure function of its arguments; tests fix the time, so the boundaries at 10 and 15 minutes are exact.

### T07 — No priority, acknowledgement and fired steps
Checks: ESC-AC02, ESC-AC11
Depends on: T06
Files: src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Extends T06 in the same function; decisions D9 and the not_applicable status.

### T08 — Suggested priorities never escalate
Checks: ESC-AC18, SEC-03
Depends on: T07
Files: src/relay/escalation/evaluate.py, tests/escalation/test_escalation_acceptance.py, tests/escalation/test_escalation_policy.py
Risk: high
Sensitive: yes
Untrusted input: yes
Tier: T2
Why: The agent builds its fixture by reading Lab 2.1's injection ticket TK32, which is untrusted input, so the task is capped at T2 whatever the other answers.

### T09 — Documents for delivery carry no task content
Checks: ESC-AC27, SEC-04, SEC-05
Depends on: T02, T06
Files: tests/escalation/test_escalation_acceptance.py, tests/escalation/test_escalation_policy.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: A privacy guardrail (PRD G3); the policy tests read the spec's data rules, so the security reviewer reviews both.

### T10 — Business hours arithmetic
Checks: ESC-AC12
Depends on: T06
Files: src/relay/escalation/hours.py, tests/escalation/test_escalation_hours.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: A pure function; its tests are worked by hand from B3 and checked against a minute-by-minute oracle, so a wrong window shows up as a failing example, not a reviewer's hunch.

### T11 — Rules for P2 to P4
Checks: ESC-AC12, SEC-02
Depends on: T05, T10
Files: src/relay/escalation/rules.py, src/relay/escalation/model.py, tests/escalation/test_escalation_acceptance.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: Widens what validation accepts, in a security-owned file; the MINOR version rests on every 1.0.0 test of accepted input still passing unchanged.

### T12 — Rule storage and audit
Checks: ESC-AC05, ESC-AC22
Depends on: T11
Files: src/relay/escalation/store.py, src/relay/escalation/engine.py, tests/escalation/test_escalation_engine.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: New tables owned by the engine (ADR-011); the audit entry's before and after are asserted field by field.

### T13 — Priorities, suggestions and acknowledgement
Checks: ESC-AC01, ESC-AC03, ESC-AC18, ESC-AC19
Depends on: T12
Files: src/relay/escalation/engine.py, tests/escalation/test_escalation_engine.py, tests/escalation/test_escalation_properties.py
Risk: high
Sensitive: yes
Untrusted input: yes
Tier: T2
Why: The fuzz test for suggestions includes injected instructions modelled on Lab 2.1's ticket TK32, which is untrusted input, so the task is capped at T2.

### T14 — Messages for delivery
Checks: ESC-AC15, ESC-AC17, ESC-AC27, SEC-06
Depends on: T09
Files: src/relay/escalation/delivery.py, tests/escalation/test_escalation_delivery.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: Customer messages and a signature. The tests check the signature with the standard library's hmac, never with the code under test, and the renderers receive no Task.

### T15 — The evaluation pass and outbox
Checks: ESC-AC08, ESC-AC11, ESC-AC15, ESC-AC27
Depends on: T13, T14
Files: src/relay/escalation/engine.py, tests/escalation/test_escalation_engine.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: Fires steps and writes messages in one transaction; D9's "never twice" is held by the fired table's primary key and tested by running the pass twice.

### T16 — The flood cap
Checks: ESC-AC23
Depends on: T15
Files: src/relay/escalation/engine.py, src/relay/escalation/store.py, tests/escalation/test_escalation_engine.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: Counts emails across all rules in the same transaction as the send (ADR-007); the P1 exemption stays an open question, pinned by a test.

### T17 — HTTP rule routes
Checks: ESC-AC05, ESC-AC21, ESC-AC24, SEC-01
Depends on: T12
Files: src/relay/service/escalation_routes.py, src/relay/service/app.py, tests/test_service_escalation.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: The trust boundary for rule changes; every route's refusals are tested before the route exists (SEC-07).

### T18 — OpenAPI contract for the routes
Checks: ESC-AC05, ESC-AC24
Depends on: T17
Files: specs/001-escalation-rules/contracts/escalation-api.openapi.json, tests/test_service_openapi.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: The route contract references the JSON Schema; a contract test compares it with the routes and the responses.

### T19 — Abuse, fuzz and property tests
Checks: SEC-07, SEC-03
Depends on: T15, T17
Files: tests/test_service_escalation.py, tests/escalation/test_escalation_properties.py
Risk: high
Sensitive: yes
Untrusted input: yes
Tier: T2
Why: The fuzz corpus includes model output and injected ticket text, which is untrusted input, so the task is capped at T2.

### T20 — The engine calls no other service
Checks: ESC-AC31, SEC-05
Depends on: T15
Files: tests/escalation/test_escalation_policy.py
Risk: medium
Sensitive: no
Untrusted input: no
Tier: T2
Why: A policy test on imports and outbox channels; it cannot see a call made through an allowed module, which review covers.

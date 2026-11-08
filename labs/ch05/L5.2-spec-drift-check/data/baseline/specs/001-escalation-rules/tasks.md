# Tasks — Escalation rule evaluation

Spec: ESC-SPEC-1@1.0.0
Planned by: sam.o
Reviewed by: aisha.r (T04, T05, T08, T09)

Each task is one pull request. Checks lists the criteria and security constraints the task's tests cover. Tiers follow Chapter 1, Table 1.6: a task whose agent reads untrusted input is capped at T2, and a sensitive task never runs at T4.

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
Why: The agent builds its fixture from Lab 2.1's injection ticket TK32, which is untrusted input, so the task is capped at T2 whatever the other answers.

### T09 — Documents for delivery carry no task content
Checks: ESC-AC27, SEC-04, SEC-05
Depends on: T02, T06
Files: tests/escalation/test_escalation_acceptance.py, tests/escalation/test_escalation_policy.py
Risk: high
Sensitive: yes
Untrusted input: no
Tier: T2
Why: A privacy guardrail (PRD G3); the policy tests read the spec's data rules, so the security reviewer reviews both.

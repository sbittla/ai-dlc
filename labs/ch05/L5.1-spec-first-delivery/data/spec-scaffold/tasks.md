# Tasks — Escalation rule evaluation

Spec: ESC-SPEC-1@1.0.0
Planned by: sam.o

Each task is one pull request. Checks lists the criteria and security constraints the task's tests cover. Tiers follow Chapter 1, Table 1.6: a task whose agent reads untrusted input is capped at T2, and a sensitive task never runs at T4. Sensitive means irreversible or sensitive in Chapter 1's sense (data deletion, customer messages, money, secrets, personal data or security controls).

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


<!-- TO COMPLETE: tasks T04 onwards. Every criterion and security constraint in the spec needs a task that checks it; give each task a risk, a tier and a reason. -->

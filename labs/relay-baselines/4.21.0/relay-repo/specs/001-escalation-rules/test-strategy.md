# Test strategy — Escalation rules engine

Spec: ESC-SPEC-1@1.1.0
Owner: sam.o (tech lead) · Security reviewer: aisha.r · Agreed: 2026-11-30

## Rules

1. **Tests before code.** For every task from T10 on, a person writes or approves the tests, sees each fail for the right reason (`NotImplementedError`, or the assertion the criterion predicts), and commits them before the code. An agent may draft tests; it may not approve them, and it may not change an approved test in the pull request that makes it pass.
2. **Independent oracles.** An expected value comes from the spec, a hand-worked example written beside the test, a standard-library recomputation (for example `hmac` for signatures), a law the code does not read (the zones' daylight-saving rules), or a slow obvious reference implementation. Never from running the code under test. Lab 8.1's oracle check (OI01 to OI03) runs on every test change.
3. **Names.** A test that checks a criterion is named after it (`test_ESC_AC27_...`). Security constraints with policy tests are named `test_SECnn_...`.
4. **Mutation score.** For `rules.py`, `evaluate.py`, `hours.py` and `delivery.py`, at least 90% of non-equivalent mutants are killed (policy `relay-mutation-v1`, Lab 8.2). Every survivor is listed in the pull request, with a test added or a reviewed reason recorded. The analysis runs nightly, and on pull requests that change one of those four modules.
5. **Test data.** Synthetic only. No production task titles, names or addresses in tests or fixtures; Confidential-looking values such as "Customer 4471 card data exposed" are invented for the criterion. Secrets in tests are labelled test-only and open nothing.
6. **Flaky tests.** No test reads a clock, the network or a random source without a fixed seed. A test that fails and then passes on rerun with no change is quarantined within one working day: it is marked, still runs, and does not block merges for at most 10 working days, with an owner, while its cause is fixed. If it is not fixed in time, the tech lead decides whether to fix, rewrite or delete it, and records why. Quarantine never applies to a test named after a criterion or a security constraint.

## Risks and the levels that test them

| Risk | Impact | Levels | Main evidence |
| --- | --- | --- | --- |
| A step fires early, late or twice | A person is paged wrongly, or not at all (G1) | Unit, property (state machine), engine | `test_escalation_acceptance.py`, `test_escalation_properties.py`, `test_escalation_engine.py` |
| Business hours counted wrongly | P2 to P4 escalations at the wrong hour (ESC-R07) | Unit by example, differential, property | `test_escalation_hours.py`, `test_escalation_properties.py` |
| Task content leaves Relay | Customer data in email or webhooks (G3, ESC-N07) | Policy, engine end to end, contract | `test_escalation_delivery.py`, `test_escalation_policy.py` |
| A forged or altered webhook is accepted by a customer | Customers act on fake events (ESC-R09) | Unit with an independent HMAC | `test_SEC06...`, `test_ESC_AC15...` |
| A rule changed without permission, or unaudited | Data to the wrong people (ESC-N03) | API (refusal matrix), engine | `test_service_escalation.py` |
| A malformed body or model output breaks the service | Outage, or a suggestion that escalates (SEC-03, SEC-07) | Fuzz | `test_service_escalation.py`, `test_escalation_properties.py` |
| Routes drift from their contract | Callers break (B7) | Contract (OpenAPI and JSON Schema) | `test_service_openapi.py`, `test_escalation_contract.py` |
| Weak assertions that pass whatever the code does | Every risk above, silently | Mutation testing | Lab 8.2's report on this suite |

## Not tested here

Transport across TB3 and TB4 (no adapters yet); load and latency (Chapter 17); runtime checks of ESC-N09 (Chapter 16); the web client.

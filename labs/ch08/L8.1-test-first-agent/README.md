# Lab 8.1 — Test-First Feature with an Agent

| | |
| --- | --- |
| Chapter | 8 — Test-First with Agents |
| Type | Core (Builder, Platform, Security) |
| Time | 4 hours |
| Cost ceiling | $0. Runs locally; no cloud and no model calls. If you ask a coding agent to help, it runs under your own subscription |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). No other packages |

## Brief

In late November a coding agent built Relay's escalation emails, webhook events and business hours in one session, and wrote their tests in the same session. All 14 tests passed. One of them asserted that the email subject carries the first 22 characters of the task's title, which ESC-AC27 forbids. Chapter 8 tells the story; `data/agent-pr/` holds the agent's code and tests.

You will build the same two parts the other way round. First you write the tests, from spec ESC-SPEC-1 1.1.0, and see them fail for the right reason. Then the code is written, by you or an agent, until they pass. A grader checks three things about your tests: they fail on the starter's stubs with `NotImplementedError` from Relay's code, they pass on a correct implementation, and they catch nine seeded bugs. An oracle-independence check refuses any test whose expected value comes from the code under test.

This release is Relay **4.20.0**: the full escalation engine, with storage, audit, the evaluation pass, delivery messages, business hours for P2 to P4 rules, the flood cap and HTTP rule routes. Everything except the two modules you build test-first is provided.

## Tracks

| Step | Builder | Platform | Security |
| --- | ---: | ---: | ---: |
| 1. Read the incident, the spec and the test strategy | 20 min | 20 min | 20 min |
| 2. Write the business-hours tests first | 50 min | 50 min | 50 min |
| 3. Write the delivery tests first | 40 min | 40 min | 40 min |
| 4. Implement the oracle check | 30 min | 30 min | 30 min |
| 5. Grade: red for the right reason | 15 min | 15 min | 15 min |
| 6. Implement (Builder), wire the gate (Platform) or attack the routes (Security) | 55 min | 55 min | 55 min |
| 7. Replay the incident | 15 min | 15 min | 15 min |
| 8. Test review record | 15 min | 15 min | 15 min |
| **Total** | **240 min** | **240 min** | **240 min** |

- **Builder:** in step 6, implement `add_business_minutes` and the four message builders.
- **Platform:** in step 6, copy the reference code (bash, from `starter/`: `cp ../solution/relay-repo/src/relay/escalation/hours.py ../solution/relay-repo/src/relay/escalation/delivery.py relay-repo/src/relay/escalation/`; PowerShell: `Copy-Item ../solution/relay-repo/src/relay/escalation/hours.py, ../solution/relay-repo/src/relay/escalation/delivery.py relay-repo/src/relay/escalation/`). Spend the time on 6P.
- **Security:** in step 6, copy the reference code as Platform does, and spend the time on 6S.

## What you will practise

- Writing tests **before** the code, from acceptance criteria and spec sections, with expected values worked by hand.
- Seeing a test **fail for the right reason**: `NotImplementedError` from the code under test, not a typo in the test.
- Keeping **test oracles independent** of the code that generates the answer.
- Measuring a suite against **seeded bugs**, including one that a criterion's own example cannot catch.
- **Red, green, refactor** with an agent in the loop, and the review step that comes before the code.

## Folder layout

```
L8.1-test-first-agent/
├── data/
│   ├── prd-v1.1.md                ← PRD v1.1 (input): D10 weekends, D11 daylight saving; the P1 flood-cap question carried forward
│   ├── agent-pr/                  ← the incident: tests/ is input; src/ is GENERATED from the reference
│   ├── variants/                  ← GENERATED: nine seeded bugs (H1-H5 business hours, D1-D4 delivery) and manifest.json
│   └── relay-4.19.0-manifest.json ← GENERATED: SHA-256 of canonical 4.19.0, to prove what 4.20.0 changed
├── scripts/generate_data.py       ← writes the GENERATED files (deterministic, byte-identical on every platform)
├── starter/
│   ├── testfirst/
│   │   ├── oracle.py              ← TODO: tainted_names, check_oracles (OI01-OI03)
│   │   ├── grade.py               ← provided: runs your tests against the stubs, the reference and the bugs
│   │   ├── plugin.py              ← provided: pytest plugin that records why each test failed
│   │   ├── incident.py            ← provided: replays the opening incident
│   │   └── report.py              ← provided: incident, grade and release reports
│   └── relay-repo/                ← Relay 4.20.0 in progress
│       ├── specs/001-escalation-rules/   ← spec 1.1.0, tasks, contracts (JSON Schema, OpenAPI), test-strategy.md
│       ├── src/relay/escalation/  ← TODO (Builder): hours.add_business_minutes; delivery's four builders
│       └── tests/escalation/      ← TODO: test_escalation_hours.py and test_escalation_delivery.py (stubs)
├── solution/                      ← reference solution (instructors; read only after finishing)
├── templates/test-review.md
├── tests/                         ← test_oracle.py (hand-checkable), test_test_first.py, test_relay.py, test_golden.py
└── evidence/                      ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's folder.

Until you finish, every failing test stops with `NotImplementedError`. Relay's own suite runs too: change to `starter/relay-repo` and run `python -m pytest -q`. The grader copies Relay to a temporary folder for each run, so it never changes your files.

## Steps

### 1. Read the incident, the spec and the test strategy (20 min)

Read `data/agent-pr/tests/escalation/test_agent_delivery.py`, then `starter/relay-repo/specs/001-escalation-rules/spec.md` sections B3, B5 and "Terms at this boundary", and `test-strategy.md` next to it. For each of the agent's 14 tests, write down where its expected value came from: the spec, a hand calculation, or the code itself.

### 2. Write the business-hours tests first (50 min)

Replace the five stubs in `starter/relay-repo/tests/escalation/test_escalation_hours.py` with real tests, and add more. Work each expected time out by hand from B3, D10 and D11, and write the local offset in a comment. ESC-AC12's own example is not enough: one seeded bug passes it.

```bash
cd starter/relay-repo
python -m pytest -q tests/escalation/test_escalation_hours.py
```

Every test should now fail with `NotImplementedError` raised in `src/relay/escalation/hours.py`. A test that passes, or fails with a `NameError` or `TypeError`, is not testing the missing code yet.

### 3. Write the delivery tests first (40 min)

Do the same in `test_escalation_delivery.py` for ESC-AC15, ESC-AC17 and ESC-AC27, through `save_rule`, `set_priority`, `run_pass` and the outbox. Recompute the signature with the standard library's `hmac`; never call `relay.escalation.delivery.sign` for the expected value. Take the title's parts from the criterion's own words.

### 4. Implement the oracle check (30 min)

Implement `tainted_names` and `check_oracles` in `starter/testfirst/oracle.py`. The docstrings are the specification; `tests/test_oracle.py` checks each rule on inputs you can verify by hand.

```bash
python -m pytest -q tests/test_oracle.py
```

### 5. Grade: red for the right reason (15 min)

```bash
cd starter
python -m testfirst.report grade > ../evidence/grade-red.md
cd ..
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

The report must show every test failing on the stubs with `NotImplementedError` from `src/relay`, every test passing on the reference, all nine seeded bugs caught, and no blocking oracle finding. If a bug is not caught, read its file in `data/variants/` and ask which sentence of the spec your tests did not check.

### 6. Implement until green (Builder, 55 min)

Implement `add_business_minutes` in `relay-repo/src/relay/escalation/hours.py`, and `escalation_email`, `escalation_event`, `event_body` and `sign` in `delivery.py`. If you use a coding agent, give it the spec, task T10 or T14 from `tasks.md`, and your approved tests, and tell it not to edit the tests. Then:

```bash
cd starter/relay-repo
python -m pytest -q
python tools/lint.py
```

### 6P. Wire the gate (Platform, 55 min)

Write `evidence/ci-test-first.yml`: a `test-first` job that runs `python -m testfirst.report grade --gate` from a pinned copy of the lab tools, plus Relay's suite. Add `test-first` to the required checks in a copy of Relay's `governance/branch-protection.json` in `evidence/`. In `evidence/test-review.md` section 6, explain why the grader must not run from the pull request it grades, and how a reviewer sees that a test commit came before the code commit.

### 6S. Attack the routes (Security, 55 min)

Read `relay-repo/tests/service_helpers.py`'s refusal matrix against spec B7, and `relay-repo/tests/test_service_escalation.py`'s fuzz tests. Write `evidence/abuse-cases.md` with at least five abuse cases the matrix does not yet name (for example a rule name carrying an email header, a 64-character rule ID collision across projects, or model output passed to `record_suggestion`), and add tests for two of them in `relay-repo/tests/test_service_abuse.py`. Every new test must pass on the reference code and be read against the spec: `tests/test_relay.py` runs your file against a copy of the reference repository, and skips while the file does not exist.

### 7. Replay the incident (15 min)

```bash
cd starter
python -m testfirst.report incident > ../evidence/incident.md
cd ..
```

Answer: the agent's tests all pass and cover most lines; which approved tests fail on the agent's code, and which of the agent's tests would your oracle check have refused? Why does the agent's own test named after ESC-AC27 pass?

### 8. Test review record (15 min)

Complete `templates/test-review.md` in `evidence/`. A colleague, or your instructor, reviews your tests against the criteria before step 6, and signs section 5.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/grade-red.md` | The grader's report before the code: every test red for the right reason, all nine bugs caught |
| `evidence/incident.md` | The incident report, with your answers to step 7 |
| `evidence/test-review.md` | Every template section, signed by a reviewer who is neither the author nor an agent |
| `evidence/ci-test-first.yml`, `evidence/branch-protection.json` | Platform track only |
| `evidence/abuse-cases.md`, `relay-repo/tests/test_service_abuse.py` | Security track only |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> Before any code existed, our 18 business-hours tests and 7 delivery tests all failed with NotImplementedError from src/relay, and all passed on the reference. ESC-AC12's example alone did not catch H1, which reads the windows in UTC: in Berlin in November, 21:00 local is 20:00 UTC, and 06:00 to 22:00 UTC happens to give the same 09:00 local answer. Our test for a 05:30 start caught it. The agent's tests pass on its own code with 88.6% line coverage of delivery.py, yet four of them compute the expected value with the code under test, and its ESC-AC27 test checks only the whole title, so a 22-character prefix passes. The reviewer read every test against its criterion before the code was written.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| "fail for another reason" lists a test | The test errors before it reaches Relay's code: a typo, a wrong fixture name, or an import from a module that does not exist. |
| "pass before the code exists" lists a test | It tests something the starter already provides, or asserts nothing about the missing code. Move it, or make it reach `add_business_minutes` or the builders. |
| A seeded bug is "not caught" | Read `data/variants/<id>/` against `solution/relay-repo/...`: the diff is one fault. Write the test the spec implies. |
| OI01 on a test you believe is independent | The expected value is computed by calling, or using the result of, something imported from `relay.escalation`. Recompute it with the standard library or write the literal. |
| Tests time out on the grader | The grader runs pytest 11 times. A test that loops over years of minutes is too slow; test the boundary instead. |
| `test_changes_since_4_19_0...` fails | You added or changed a Relay file outside the lists in `tests/test_relay.py`. |

## Cleanup

Nothing to clean up. The grader's copies live in your system's temporary folder and are deleted after each run.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Tests written first | 3 | Every test fails on the stubs for the right reason and passes on the reference; ESC-AC12, ESC-AC15, ESC-AC17 and ESC-AC27 each have named tests |
| Bugs caught | 2 | All nine seeded bugs make at least one test fail |
| Independent oracles | 2 | No blocking oracle finding; every expected time has a hand calculation beside it |
| Implementation (Builder), gate (Platform) or abuse tests (Security) | 2 | Builder: Relay's suite and lint pass. Platform: the gate is a required check run from a pinned copy. Security: five abuse cases, two tested |
| Review record | 1 | A reviewer who is not the author signed the tests before the code, and the record names what the tests cannot see |

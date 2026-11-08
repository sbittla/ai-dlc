# Lab 5.2 — Spec Drift Check in CI

| | |
| --- | --- |
| Chapter | 5 — Specification-Driven Development |
| Type | Stretch (Builder, Platform) |
| Time | 3 hours |
| Cost ceiling | $0. Runs locally; no cloud and no model calls |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

Relay 4.18.0's escalation slice has four artifacts that must say the same thing: the spec, the JSON Schema contract, the code and the tests. Lab 5.1 checked them once, at approval. Every later pull request, by a person or an agent, can make them disagree.

You will build a **drift check**: a program that reads the four artifacts, compares them structurally, and exits with a status CI can act on. You will run it on eight seeded drifts, and find out which ones it catches, which ones the test suite catches, and which ones nothing automatic catches.

`data/baseline/` is Relay 4.18.0, copied from Lab 5.1's reference solution. `data/scenarios/` holds nine scenarios: the baseline, six **structural** drifts (names, types, enums, versions, criterion IDs) and two **behavioural** drifts (the code's or a test's meaning changes, and every name stays the same).

## What you will practise

- Comparing **spec ↔ contract ↔ code ↔ tests** by reading them, never running them.
- A **CI gate with explicit exit codes**: 0 pass, 1 blocking drift, 2 cannot check (fails closed).
- Telling **structural** from **behavioural** drift, and knowing which check sees which.
- Writing an honest record of what a passing drift gate does not prove.

## Folder layout

```
L5.2-spec-drift-check/
├── data/
│   ├── baseline/                ← Relay 4.18.0 (input, copied from Lab 5.1; not generated)
│   └── scenarios/NN-name/       ← GENERATED: scenario.json and the changed files under files/
├── scripts/generate_data.py     ← writes data/scenarios/ (deterministic; byte-identical on every platform)
├── starter/driftcheck/
│   ├── extract.py               ← provided: reads the four artifacts into Facts (ast and JSON only)
│   ├── compare.py               ← TODO: 4 comparisons; the catalogue and detect() are provided
│   ├── gate.py                  ← provided: the CI gate and its exit codes
│   └── report.py                ← provided: every scenario, optionally with its test suite
├── solution/driftcheck/         ← reference solution (instructors; read only after finishing)
├── templates/                   ← drift-record.md, spec-drift.yml (a CI job)
├── tests/                       ← test_compare.py (hand-checkable), test_golden.py (the chapter's numbers)
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it. Run pytest from this lab's folder. Until you finish, every failing test stops with `NotImplementedError`. The golden tests run each scenario's suite, so a full run takes about 15 seconds.

## Steps

### 1. Read the artifacts and the extractor (20 min)

Read `data/baseline/specs/001-escalation-rules/spec.md` (Behavior and Data rules), its contract, `src/relay/escalation/model.py` and the three test modules' docstrings. Then read `starter/driftcheck/extract.py`. For each kind of fact, write down which artifact states it and which others repeat it.

### 2. Implement the comparisons (70 min)

| Function | What it decides |
| --- | --- |
| `compare_versions` | Do the spec, contract, code and every test module name the same spec version? |
| `compare_fields` | Has every contract field a code field of the same JSON type, and a data rule in the spec? |
| `compare_enums` | Do statuses, error codes and priorities match between contract, code and spec tables? |
| `compare_criteria` | Has every spec criterion a test, and does every criterion-named test name a spec criterion? |

```bash
python -m pytest -q tests/test_compare.py
```

### 3. Run the gate on the scenarios (25 min)

```bash
cd starter
python -m driftcheck.gate ../data/baseline; echo "exit $?"
python -m driftcheck.report --baseline ../data/baseline --scenarios ../data/scenarios --run-tests --details > ../evidence/drift-report.md
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead. In PowerShell, use `echo "exit $LASTEXITCODE"`.

For each scenario, compare the gate's column with the test suite's. Find the scenario where the gate fails and the tests pass, and the one where the tests fail and the gate passes.

### 4. The drift nobody caught (25 min)

Read scenario 08's two changed files. Every artifact still agrees, and every test passes. Write down what ESC-AC10 requires, and which line of which file now fails to check it. Then decide what would have caught it: a reviewer reading the test against the criterion, a mutation test, or a stricter test. Say which you would require, and at what cost.

### 5. Seed one drift of your own (20 min)

Copy `data/scenarios/04-status-added-in-code` to `evidence/scenarios/09-mine/`: from the lab folder, `mkdir -p evidence/scenarios && cp -r data/scenarios/04-status-added-in-code evidence/scenarios/09-mine` in bash, or `New-Item -ItemType Directory -Force evidence/scenarios; Copy-Item -Recurse data/scenarios/04-status-added-in-code evidence/scenarios/09-mine` in PowerShell. Edit its scenario.json title to state your prediction, then change one file under `files/` in a way you predict the gate will catch, or will miss. Run it:

```bash
cd starter
python -m driftcheck.report --baseline ../data/baseline --scenarios ../evidence/scenarios --run-tests --details
```

### 6. Wire it into CI (Platform: 20 min; Builder: read only)

Read `templates/spec-drift.yml`. Copy it to `evidence/` and complete it for your CI system. Decide where the checker comes from, so that a pull request cannot weaken the check that reviews it, and add `spec-drift` to the required status checks in a copy of `data/baseline/governance/branch-protection.json` in `evidence/`.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/drift-report.md` | The report on all nine scenarios, with test results and details |
| `evidence/drift-record.md` | Every template section completed |
| `evidence/scenarios/09-mine/` | Your seeded drift, with your prediction in its scenario.json title |
| `evidence/spec-drift.yml` | Platform track: the completed CI job |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> Of six structural drifts the gate found six, and five failed it; scenario 06's extra test for ESC-AC15 only warns. Of two behavioural drifts it found none. The test suite caught one of the two: moving `>=` to `>` fails three tests, including ESC-AC08's at exactly 10 minutes. It did not catch scenario 05, where `delay_minutes` became a float in the code: all 64 tests pass, because they only use whole minutes, and the gate fails on DR012. Scenario 08 passes both: the delay message no longer names the range and the assertion that checked it was deleted in the same change. Only a reviewer who reads ESC-AC10's test against its criterion would see it, so our review checklist now asks for that on every change to a test named after a criterion.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| DR013 on every field | The data rules table needs field names in backticks; check `extract.py`'s pattern against the spec. |
| DR012 on `next_due_at` | Compare the type strings exactly as extracted: both are `null|string`. Do not reorder them yourself. |
| DR020 on PRIORITIES only | Compare enum values as sets; order does not matter. |
| Gate exits 2 | An artifact could not be read: the spec, the contract, the escalation dataclasses or the escalation tests. That is a failure, not a pass. |
| Report is slow | `--run-tests` runs nine test suites. Leave it off while you iterate. |

## Cleanup

Nothing to clean up; the report works in temporary folders.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Comparisons correct | 3 | All tests pass against `starter/` |
| Reading the results | 3 | Gate and test-suite results compared for every scenario; the drift each one alone catches is named |
| Limits | 2 | Scenario 08 explained by mechanism, with the human or automated step that would catch it and its cost |
| Own scenario | 1 | A prediction recorded before the run, and the result explained |
| CI wiring | 1 | Exit codes used correctly, 2 fails the build, and the checker cannot be changed by the pull request it checks |

# Lab 8.2 — Mutation and Property-Based Test Repair

| | |
| --- | --- |
| Chapter | 8 — Test-First with Agents |
| Type | Stretch (Builder, Platform) |
| Time | 4 hours |
| Cost ceiling | $0. Runs locally; no cloud and no model calls |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). No other packages: the mutation tool and the property helper are small standard-library programs, so you can read all of them |

## Brief

A coding agent wrote 29 tests for the escalation engine's pure core: rule validation, evaluation and business hours. They all pass, and they execute 97% of the lines. Mutation testing asks a harder question: if the code were wrong in a small, specific way, would any test notice? For this suite, most of the time, no.

You will implement the core of a mutation tool, measure the agent's suite, and read its survivors. Then you will repair the suite: exact expectations, boundary cases and refusal codes, plus properties checked on generated inputs against oracles the code does not share. The policy, `relay-mutation-v1`, asks for 90% of non-equivalent mutants killed in every module. You will also decide, with reasons, which survivors are equivalent mutants that no test can kill.

## What you will practise

- **Mutation testing**: operators, killed and surviving mutants, the score, and why line coverage is a different question.
- **Equivalent mutants**: telling a mutant no input can distinguish from one your tests simply do not reach.
- **Property-based testing** with a seeded generator and shrinking, and **differential testing** against a slow obvious oracle.
- The **limits of a score**: it is a ratio over the mutants a tool chose to make.

## Folder layout

```
L8.2-mutation-property-repair/
├── data/
│   ├── relay-repo/               ← GENERATED: Relay 4.20.0's src, escalation tests and spec, copied from Lab 8.1
│   ├── weak-suite/test_agent_suite.py   ← the agent's 29 tests (input; do not edit)
│   ├── mutation-policy.json      ← relay-mutation-v1: targets, operators, the 90% threshold (input)
│   └── equivalent-mutants.json   ← mutants recorded as equivalent, each with a reason and a reviewer (input)
├── scripts/generate_data.py      ← writes data/relay-repo (deterministic)
├── starter/
│   ├── mutate/
│   │   ├── operators.py          ← TODO: candidates (the six operators)
│   │   ├── runner.py             ← provided: runs a suite against each mutant, in process
│   │   ├── score.py              ← TODO: score, gate
│   │   └── report.py             ← provided: the mutation report
│   └── suite/test_repaired.py    ← TODO: your repair, starting as a copy of the agent's suite
├── solution/                     ← reference solution (instructors; read only after finishing)
├── templates/mutation-record.md
├── tests/                        ← test_operators_and_score.py (hand-checkable), test_golden.py
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it. Run pytest from this lab's folder. Until you finish, every failing test stops with `NotImplementedError`.

The golden tests run real mutation analyses and take about four minutes in all. Run the fast tests while you work: `python -m pytest -q tests/test_operators_and_score.py`.

## Steps

### 1. Read the suite, the policy and the runner (20 min)

Read `data/weak-suite/test_agent_suite.py`, `data/mutation-policy.json` and the docstring of `starter/mutate/runner.py`. For five of the agent's tests, write down a one-character change to the code that the test would not notice.

### 2. Implement the operators (40 min)

Implement `candidates` in `starter/mutate/operators.py`. Its docstring lists every operator and the exact tuple each one produces.

```bash
python -m pytest -q tests/test_operators_and_score.py -k "operator or chained or mutant"
```

### 3. Implement the score and the gate (20 min)

Implement `score` and `gate` in `starter/mutate/score.py`. The threshold is inclusive. A killed mutant listed as equivalent counts as killed.

```bash
python -m pytest -q tests/test_operators_and_score.py
```

### 4. Measure the agent's suite (25 min)

```bash
cd starter
python -m mutate.report --data ../data --suite agent --modules rules,evaluate,hours > ../evidence/agent.md
cd ..
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead. The run takes about a minute.

Compare line coverage with the score, module by module. Group the survivors: missing refusal codes, boundaries tested only from inside, expected values computed by the code, and a data table no test reads.

### 5. Repair the suite (70 min)

Edit `starter/suite/test_repaired.py`. Keep each agent test's intent, and make it exact: assert the code, test 5 and 240 as well as 10, compare with a hand-worked time. Add at least two properties with `props.for_all` (in `data/relay-repo/tests/escalation/props.py`), with oracles the code does not share. Relay's `test_escalation_properties.py` has the daylight-saving law for every zone, which you may import. Delete `test_repairs_written` when you start.

```bash
cd starter
python -m mutate.report --data ../data --suite repaired --modules rules,evaluate,hours
```

### 6. Decide the survivors (30 min)

For every mutant still alive, either add a test that kills it or decide it is equivalent. An equivalent mutant behaves like the original for every input the spec allows. Write each decision in `evidence/mutation-record.md`, with the input you tried. Do not add your own entries to `data/equivalent-mutants.json` without a reviewer: the report prints the score with and without equivalence claims for exactly this reason.

### 7. Relay's own suite (15 min)

```bash
cd starter
python -m mutate.report --data ../data --suite relay > ../evidence/relay.md
cd ..
```

This mutates `delivery.py` too. Read the one recorded equivalent mutant there and decide whether you agree, or whether the spec should be tightened instead.

### 8. Write the record (20 min)

Complete `templates/mutation-record.md` in `evidence/`.

**Platform track:** in step 6, also write `evidence/ci-mutation.yml`: a nightly job, not a per-pull-request one, that runs the Relay report with `--gate` and opens an issue on failure. Say in the record why the run is nightly and what keeps the equivalence list honest.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/agent.md`, `evidence/relay.md` | The generated reports |
| `evidence/mutation-record.md` | Every template section: scores before and after, every survivor's decision, the limits of the score |
| `suite/test_repaired.py` (in `starter/`) | Your repaired suite: the gate passes, with at least two properties |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The agent's 29 tests execute 97% of the core's lines and kill 26.2% of its 369 mutants. In rules.py they kill 86.5%: the survivors include `<=` turned into `<` for equal delays, because no test uses two equal delays. In hours.py they kill 15.4%: 256 of 314 mutants are in the module-level constants and the daylight-saving table, which no test compares with anything independent. Our repair kills 99.7% after two equivalent mutants are excluded, and 99.0% with no equivalence claims. One mutant survives: reading "17:30" as 16:30, because none of our examples has a time with minutes. We added none for it yet and recorded why. A score this high says that these six operators find nothing more; it does not say the tests are complete.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| "the suite fails on unmutated code" | A test in your repaired suite fails on the real code. Run it with pytest from `data/relay-repo` to see why. |
| A mutant you killed still shows as survived | The killing test is excluded because it failed on the original, or it needs a pytest fixture the runner does not support (it supports plain tests, `pytest.raises` and `parametrize`). |
| The report is very slow | A property with many runs, or one that loops over many minutes, runs once per mutant. Lower `runs` or shrink the input range. |
| Equivalent count higher than expected | Only ids in `data/equivalent-mutants.json` count, and only while no test kills them. |
| `ModuleNotFoundError: escalation_fixtures` | Run the report from `starter/` with `--data ../data`; the runner adds the test helpers' folder to the path. |

## Cleanup

Nothing to clean up. The runner caches bytecode in your system's temporary folder (`relay-mutate-pycache`); delete it if you like.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Operators and score correct | 3 | `tests/test_operators_and_score.py` and the golden tests pass against `starter/` |
| Repair | 3 | Your suite passes the gate with exact, independent expectations and at least two properties |
| Survivors decided | 2 | Every survivor has a test or a reason, and each claimed equivalent names an input you tried |
| Limits stated | 2 | The record explains coverage against score, what the operator set cannot see, and why the score is not a target |

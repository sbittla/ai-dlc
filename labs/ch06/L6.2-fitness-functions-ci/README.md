# Lab 6.2 — Fitness Functions in CI

| | |
| --- | --- |
| Chapter | 6 — Architecture, Decisions and Fitness Functions |
| Type | Stretch |
| Time | 3 hours |
| Cost ceiling | $0. Runs locally; no cloud and no model calls |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

ADR-007 says Relay is a modular monolith: domain modules do not know about the HTTP service or the worker, the service reaches the worker only through its public interface, only the service touches the network, and every new dependency needs a decision record. A sentence in a decision record does not stop an agent from writing `from ..worker.queue import TriageQueue`. A test does.

You will turn ADR-007's and ADR-008's rules into fitness functions that read Relay's source and fail the build when a rule is broken. Then you will measure them on ten seeded cases: seven they should catch, two they cannot, and one control that should pass. The tool is honest only if it reports its misses.

## What you will practise

- Writing **architecture rules as code**, each linked to the ADR it enforces.
- Building an **import graph** from source with `ast`, including relative imports, without running the code.
- **Dependency rules** (every third-party import declared and recorded in an ADR) and **cycle detection**.
- Measuring a gate on **seeded violations**, including known blind spots and a control case.
- Running it as a **required status check** with an exit code.

## Folder layout

```
L6.2-fitness-functions-ci/
├── data/
│   ├── relay-repo/               ← Relay 4.19.0's source, docs/adr and pyproject.toml, copied unchanged from Lab 6.1
│   ├── rules.json                ← GENERATED: FF001-FF006, each with its ADR
│   └── seeded/                   ← GENERATED: V01-V10 overlays (files that replace or add files) and manifest.json
├── scripts/generate_data.py      ← writes rules.json and seeded/ from data/relay-repo (byte-identical everywhere)
├── starter/fitcheck/
│   ├── graph.py                  ← TODO 1: imports_of; provided: load_tree (with overlay), module_name, build_graph
│   ├── rules.py                  ← TODO 2-4: check_layers, check_dependencies, find_cycles; check_network provided
│   └── report.py                 ← provided: findings, --overlay, --seeded, --gate
├── solution/fitcheck/            ← reference solution (instructors; read only after finishing)
├── templates/                    ← fitness-job.yml (a CI job), fitness-review.md
├── tests/                        ← test_fitcheck.py (hand-checkable), test_golden.py (the chapter's numbers), test_data.py
└── evidence/                     ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's folder.

Until you finish, every failing test stops with `NotImplementedError`.

## Steps

### 1. Read the rules and the decisions (15 min)

Read `relay-repo/docs/adr/ADR-007-*.md` and `ADR-008-*.md` in `data/`, then `data/rules.json`. Match each rule to a sentence in an ADR. Note the three pattern forms: `x`, `x.*` and `x.+`. Why does FF002 use `relay.worker.+` and FF001 `relay.worker.*`?

### 2. Build the import graph (25 min)

Implement TODO 1, `imports_of` in `starter/fitcheck/graph.py`. Relative imports are the hard part: `from ..worker import X` in `relay/service/app.py` means `relay.worker`.

```bash
python -m pytest -q tests/test_fitcheck.py -k imports
```

### 3. Layer rules (30 min)

Implement TODO 2, `check_layers` in `starter/fitcheck/rules.py`. One finding per forbidden import, with the rule's ADR.

### 4. Dependencies need decisions (30 min)

Implement TODO 3, `check_dependencies`: a third-party import must be declared in `pyproject.toml` and named in an accepted ADR's `Dependency:` line. Relay 4.19.0 has no third-party imports, so the clean tree passes; V05–V07 exercise the rule.

### 5. Cycles (30 min)

Implement TODO 4, `find_cycles`: strongly connected components of the import graph, ignoring imports of a module's own ancestor packages. Tarjan's or Kosaraju's algorithm both work; so does a simpler search, at this size.

```bash
python -m pytest -q
```

### 6. Run the gate and the seeded cases (20 min)

```bash
cd starter
python -m fitcheck.report --repo ../data/relay-repo --rules ../data/rules.json --gate; echo "exit $?"
python -m fitcheck.report --repo ../data/relay-repo --rules ../data/rules.json --overlay ../data/seeded/V03 --gate; echo "exit $?"
python -m fitcheck.report --repo ../data/relay-repo --rules ../data/rules.json --seeded ../data/seeded > ../evidence/seeded.md
```

In PowerShell, use `echo "exit $LASTEXITCODE"`. On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 ../evidence/seeded.md` instead.

Read V08 and V09, the two misses. Then write your own seeded case: copy one folder in `data/seeded/` to `evidence/seeded/V11/`, change one file, and run with `--overlay`. Can you write a violation of ADR-007 that no rule could catch with static analysis, and one that a new rule could?

### 7. Wire it into CI and review its limits (30 min)

Adapt `templates/fitness-job.yml` for Relay's workflow and say which branch-protection change makes it required (Chapter 3). Relay's own `tests/test_architecture.py` already runs AR1–AR5 inside the required `tests` check; decide whether `fitness` should be a separate check. Complete `templates/fitness-review.md` in `evidence/`.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/seeded.md` | The seeded table: 9 violations, 7 caught, 2 missed, the control clean, no false alarms |
| `evidence/seeded/V11/` | Your seeded case, and in the review its expected result and the gate's exit status |
| `evidence/fitness-job.yml` | The CI job, with the branch-protection change named |
| `evidence/fitness-review.md` | Every template section completed |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> Relay 4.19.0 passes all six rules: 17 modules and 78 static imports. On the ten seeded cases the rules caught 7 of 9 violations, passed the control (a declared dependency with an accepted ADR) and raised no false alarms. V03 fired two rules: the worker importing the service broke FF003 and closed a cycle through `relay.worker`'s `__init__`. The two misses are structural. `importlib.import_module("relay.worker.queue")` is a string at run time, and `subprocess.run(["curl", ...])` reaches the network without importing a network module. Review covers the first; for the second, the worker's production sandbox will have no egress except to the model provider (Chapter 11). We kept V10's rule: a type-only import still couples the service to the queue's internals.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `from .. import __version__` resolves to `relay.service` | For a non-package module, the package is the module name without its last part; `level` 2 goes one more step up. |
| An `__init__.py` resolves one level too high | In a package's `__init__.py` the package is the module itself (`is_package=True`). |
| A cycle reported for every package | Ignore an edge whose target is an ancestor of its source (`relay.worker.runner` importing `relay.worker`). |
| `json` or `typing` flagged by FF005 | Compare the top-level name with `sys.stdlib_module_names` (Python 3.10+). |
| V07 flagged | The ADR must have `Status: accepted` and a line `Dependency: httpx`; names are compared in lower case. |
| Different results on Windows | Paths in `load_tree` are POSIX (`as_posix()`); compare with forward slashes. |

## Cleanup

Nothing to clean up. Remove `LAB_TARGET` if you set it.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Tool correct | 4 | All tests pass against `starter/` |
| Seeded evaluation | 2 | Table produced; both misses explained with the control that covers each |
| Own seeded case | 2 | A new case with its expected result, run through the gate, and a judgement on whether a rule could catch it |
| CI and ownership | 2 | The job wired as a required check; who owns the rules, and how an agent is prevented from weakening them |

# Lab 9.2 — Legacy Refactor with Characterization Tests and Parallel Agents

| | |
| --- | --- |
| Chapter | 9 — Agent-Assisted Implementation, Review and Modernization |
| Type | Stretch |
| Time | 4 hours, tight: the steps add up to 240 minutes with no slack; step 6 can be done afterwards |
| Cost ceiling | $0. Runs locally; no cloud and no model calls. The "agents" are simulated: their outputs are files in `data/worktrees/`, written for the book |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). Step 6 also uses git (any recent version) |

## Brief

Relay's notification preferences live in a module written for Relay 3.x in 2023: a global connection, a hidden clock, and muted types stored as text in two formats. On 8 December 2026 a coding agent rewrote it in one 4,067-line pull request. Its migration lost opt-outs and spam marks and dropped the legacy table; its new decision changed three behaviours nobody had written down (Chapter 9, opening incident).

You will do what the team did next. First, characterize the legacy module: run it and a candidate on thousands of generated cases, including timezone-aware times and sequences of writes, and report every difference by the behaviour it touches. Then replay the incident's migration on production-shaped synthetic data and count what it lost. Finally, integrate the five small pull requests that replaced the module, written by simulated agents in parallel worktrees: plan the order, see where two of them conflict, and check the characterization after every step.

## What you will practise

- **Characterization tests**: pinning what legacy code does, including behaviour nobody would choose, before changing it.
- **Migration review by replay**: counting rows lost on realistic data rather than reading the SQL and hoping.
- **The strangler pattern and compatibility layers**: replacing a module in steps, each with a rollback.
- **Parallel agents**: partitioning work, worktrees, integration order, and resolving a conflict.

## Folder layout

```
L9.2-legacy-refactor-characterization/
├── data/
│   ├── relay-notify/            ← GENERATED: Relay 4.22.0's notify package and tests, copied from Lab 9.1;
│   │                              its tests/notify/legacy_reference.py and corpus.py are the oracle
│   ├── prod-like.json           ← GENERATED: SYNTHETIC production-shaped rows and a day of events
│   ├── agent-pr/                ← input: the incident's migration and rewrite, reconstructed
│   ├── tasks.json               ← input: the five tasks, their files and dependencies
│   ├── worktrees/T1 … T5, T3-rebased/   ← input: each SIMULATED agent session's output files
│   └── accepted-differences.json        ← input: differences a reviewer accepted, with reasons
├── scripts/generate_data.py     ← writes the GENERATED files (deterministic)
├── starter/modernize/
│   ├── charact.py               ← TODO: compare_decisions, classify_prefs
│   ├── migration.py             ← TODO: losses
│   ├── parallel.py              ← TODO: integration_order (waves and integrate are provided)
│   └── merge.py, probe.py, paths.py, diffs.py, report.py   ← provided
├── solution/                    ← reference solution (instructors; read only after finishing)
├── templates/                   ← characterization-record.md, integration-plan.md
├── tests/                       ← test_modernize.py (hand-checkable), test_golden.py
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it. Run pytest from this lab's folder. Until you finish, every failing test stops with `NotImplementedError`. The golden tests take about ten seconds, because the parallel report integrates five worktrees and runs the tests after each.

On Windows PowerShell 5.1, `>` writes UTF-16. Where a step redirects a report to a file, use `| Out-File -Encoding utf8 <file>` instead.

## Steps

### 1. Read the legacy module and the incident's code (20 min)

Read `data/relay-notify/tests/notify/legacy_reference.py`, then `data/agent-pr/migrate_notifications.py` and `notifications_agent.py`. List every behaviour of the legacy `should_send` you can find, and every way the rewrite differs. Keep the list; step 2 will check it.

### 2. Characterize (45 min)

Implement `compare_decisions` and `classify_prefs` in `starter/modernize/charact.py`.

```bash
python -m pytest -q tests/test_modernize.py -k "compare or classify"
cd starter
python -m modernize.report characterize > ../evidence/characterize.md
cd ..
```

Compare the report with your list from step 1. A case can carry several tags, so the tag rows do not add up to the total; for each tag, find one differing case and say which change in the rewrite caused it.

### 3. Replay the incident's migration (35 min)

Implement `losses` in `starter/modernize/migration.py`.

```bash
cd starter
python -m modernize.report incident > ../evidence/incident.md
cd ..
```

For each of the two bugs in the migration, name the rows it lost and the SQL or Python that lost them. Then explain why Relay 4.22.0's `migrate_legacy` cannot lose them silently.

### 4. Read the five worktrees and predict (25 min)

Read `data/tasks.json` and the files under `data/worktrees/`. Before running anything, write in `templates/integration-plan.md` (copied to `evidence/`) which tasks can run in parallel, which files two of them both touch, and where you expect a conflict.

### 5. Plan the order and integrate (35 min)

Implement `integration_order` in `starter/modernize/parallel.py`.

```bash
cd starter
python -m modernize.report parallel > ../evidence/parallel.md
cd ..
```

Did the conflict happen where you predicted? Why does the integration re-run T3's agent rather than merge the conflict by hand, and what would you check if you merged it by hand instead?

### 6. Worktrees for real (30 min)

In a scratch folder, not this repository, create a repository with one file, then two worktrees. A fresh repository needs an identity for `git commit`: run `git config user.name "Your Name"` and `git config user.email you@example.com` inside it first.

```bash
git init scratch && cd scratch && printf 'a\nb\nc\n' > f.txt && git add f.txt && git commit -m base
git worktree add ../scratch-t2 -b t2 && git worktree add ../scratch-t3 -b t3
```

In each worktree, change line 2 differently and commit. Merge `t2` into the main branch, then `t3`, and read the conflict. Resolve it, run `git worktree list`, and remove both with `git worktree remove`. Record the commands and what each worktree shared with the others (the object store and refs) and what it did not (the working files and the index).

### 7. Characterization record (30 min)

Complete `templates/characterization-record.md` in `evidence/` for the notification module. Decide, for every tag, whether the behaviour is characterized only, or also endorsed; the spam mark's suppression of security notices is the hard one. Say who should accept each difference.

### 8. Rehearse the rollback (20 min)

Copy `data/relay-notify` to a scratch folder, and run its tests with reads rolled back: `RELAY_NOTIFY_READ_FROM=legacy PYTHONPATH=src python -m pytest -q tests/notify` (bash) or `$env:RELAY_NOTIFY_READ_FROM="legacy"; $env:PYTHONPATH="src"; python -m pytest -q tests/notify; Remove-Item Env:RELAY_NOTIFY_READ_FROM, Env:PYTHONPATH` (PowerShell). Which tests still pass, and why is that the rollback ADR-018 relies on?

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/characterize.md` | The report, and one explained case per tag |
| `evidence/incident.md` | The report, the two bugs and the lines that cause them |
| `evidence/integration-plan.md`, `evidence/parallel.md` | Your prediction before step 5, the report, and the comparison |
| `evidence/worktrees.md` | Step 6's commands, the conflict and its resolution |
| `evidence/characterization-record.md` | Every section, with an owner for each accepted difference |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The rewrite disagrees with the legacy module on 2,013 of 5,019 cases. Every case tagged security that differs is a spam-marked user: the rewrite checks for a security notice before the spam mark, so it sends what the legacy code suppressed. The replay found that the migration lost 319 opt-outs belonging to 130 users, all from lists written with ";", and 36 of 78 spam marks, all on users whose muted_types was NULL or empty: `WHERE muted_types <> ''` is never true for NULL. On the synthetic events, 388 emails went to people who had said no.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `NotImplementedError: TODO: …` from a report | That step's function is not finished; the message names it. |
| `probe failed` with an ImportError | `data/relay-notify` is missing or stale: run `python scripts/generate_data.py`. |
| `the integrated tree's tests failed` | A step's files do not work together; the message shows the failing test. If you edited `data/worktrees/`, restore it. |
| `Integrated result equals Relay 4.22.0's notify package and tests: no` | Lab 9.1's reference changed after `data/relay-notify` was generated, or a worktree was edited. |
| Golden tests fail and the numbers moved | You changed `data/`, the corpus seed (`NOTIFY_SEED`) or a worktree. Unset `NOTIFY_SEED` and regenerate. |

## Cleanup

The parallel report works in your system's temporary folder and deletes it. Remove step 6's scratch repository and worktrees with `git worktree remove` and by deleting the folders, and step 8's scratch copy.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Characterization | 3 | The tests pass, and one case per tag is explained by a specific change in the rewrite |
| Migration replay | 2 | Both bugs named with the rows they lost and the lines that lost them |
| Integration | 2 | The prediction is written before the run, the order is correct, and the conflict is explained |
| Worktrees | 1 | A real conflict between two worktrees, resolved and recorded |
| Record and rollback | 2 | Every tag decided with an owner; the rollback rehearsal's result explained |

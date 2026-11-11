# Lab 19.1 — A Dependency and Vulnerability-Fix Bot That Opens a PR with Test and Security Evidence and Requires Approval

| | |
| --- | --- |
| Chapter | 19 — Bounded Autonomy: Self-Maintaining Software |
| Type | Core (all tracks) |
| Time | 4 hours |
| Cost ceiling | $0. Runs on your machine, offline: the code host is a recording fake, the model is a script, and no package is installed |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

On Thursday 20 May 2027 a rule-based dependency bot merged a minor update of the web application's session library,
and nobody could sign in for two hours. In this lab you replay that lockout, then run the same update through Relay's
maintenance bot: a plan from the mirror, checks in the sandbox, and a guard metric on the canary. You then run the bot
end to end on a vulnerability report, from reproduction to a pull request that waits for the right person, and show
the three behaviours Chapter 19's release check asks for: a safe rejection, a blocked injection attempt and a rollback.

You have **Relay 4.31.0** in `relay-repo/`: canonical 4.30.0 plus `src/relay/maintenance/`, the bot's policy in
`maintenance/`, its registry entry and workflow, ADR-053 to ADR-056, the pipeline guard's new paths, and 121 new tests.

**About the names and the data.** `sessionkeel` is a **fictional** library, and so are ferncache, ledgerwick, mossdate,
quaymail and tallowcsv: each name returned "not found" on the public Python package index on 2026-11-10. Never install a
package by these names; if one appears on a public index, it is not this one. The lab's six "releases" of sessionkeel
are small inert modules written by `scripts/generate_data.py`. Everything in `data/` is **generated and configured**:
the incident's per-minute counts, the canary of 29 June, the replay of 60 updates (which ones regress, and which control
can see each, was chosen to show the mechanisms) and a simulated month of the bot's runs (the bot did not run in June; its runner, app and guard metric are not built, so June is a replay). Report bodies that stand for an attacker's
text are **inert labelled placeholders**, not working injections.

## What you will practise

- Reading a lockout from a per-minute record, and saying why every check passed.
- Treating a version number as a claim, and checking what changed: pinned defaults, a round trip, a guard metric.
- Running a fix through reproduction, evidence and an approval bound to the diff and the evidence.
- Showing that the bot, its owner and a non-owner cannot approve, and that every refusal is audited.
- Comparing two policies on the same updates with an exact McNemar test, and reading a small result honestly.

## Folder layout

```
L19.1-maintenance-bot/
├── relay-repo/                 ← Relay 4.31.0 (Chapter 19 branch): canonical 4.30.0 + relay.maintenance; 1,184 tests
│   ├── src/relay/maintenance/  ← reports, semver, updates, evidence, policy, proposals, agent_step, longrun, guard,
│   │                             autonomy, safety_case, tables
│   ├── maintenance/            ← policy.json (relay-maintenance-policy-v1), dst-rules.json
│   └── docs/adr/               ← ADR-053 to ADR-056
├── data/                       ← GENERATED: mirror, packages/, webapp/, incident, canary, history, outcomes, reports
├── scripts/generate_data.py
├── starter/mainlab/
│   ├── incident.py             ← TODO 1: timeline; TODO 2: controls
│   ├── worked.py               ← TODO 3: fix_vulnerability
│   ├── demo.py                 ← TODO 4: rollback (safe_rejection and injection are provided)
│   ├── measure.py              ← TODO 5: paired (month is provided)
│   ├── dst.py, world.py        ← provided
│   └── report.py               ← provided
├── solution/mainlab/           ← reference solution (instructors; read only after finishing)
├── templates/maintenance-task-review.md
├── tests/                      ← test_mainlab (hand-checkable), test_golden, test_answers, test_relay
└── evidence/                   ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. To check the reference, in bash: `LAB_TARGET=solution python -m pytest -q`.
In PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists
until it is removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's
folder. Until you finish, failing tests stop with `NotImplementedError`; `tests/test_relay.py` and `tests/test_answers.py`
pass from the start. Some checks start real, inert sandbox processes; the whole suite takes about a minute.

## Steps

### 1. Read the incident, the policy and the package (20 min)

Read Chapter 19's opening incident, ADR-053 and ADR-054, `relay-repo/maintenance/policy.json` and the docstrings of
`src/relay/maintenance/proposals.py` and `updates.py`. Then run Relay's checks:
`cd relay-repo && PYTHONPATH=src python -m pytest -q && python tools/lint.py && python tools/supplychain.py`
(PowerShell: `$env:PYTHONPATH="src"; python -m pytest -q; Remove-Item Env:PYTHONPATH`). One POSIX-only sandbox test
is skipped on Windows.

### 2. The lockout: TODO 1 (25 min)

Implement `timeline` in `incident.py`, then `cd starter && python -m mainlab.report incident`. How long was everyone
locked out, and how long were some users? Why did the page at 14:50 lead the team towards an attack?

### 3. The same update under the new policy: TODO 2 (40 min)

Implement `controls`, then `python -m mainlab.report controls > ../evidence/controls.md`. On Windows PowerShell 5.1,
`>` writes UTF-16; use `| Out-File -Encoding utf8 ../evidence/controls.md` instead. Which check would have stopped the
update before release, and which after? Why do the application's tests still pass?

### 4. The worked example: TODO 3 (50 min)

Implement `fix_vulnerability` in `worked.py`, then `python -m mainlab.report worked`. Read the evidence table: which
item is `modelled`, and why? Add one more refused approver of your own choosing to the sequence in a scratch copy,
predict its refusal code, and check it against the audit trail (`w.world.trail.records`).

### 5. The three behaviours: TODO 4 (35 min)

Implement `rollback` in `demo.py`, then `python -m mainlab.report demo > ../evidence/demo.md`. For the injection, list
the four refusals and the control that produced each, and say which controls in Table 19.4 of the chapter it did not
need. For the rollback, explain why every pre-release check passed on 2.4.3.

### 6. Comparing policies: TODO 5 (30 min)

Implement `paired` in `measure.py`, then `python -m mainlab.report replay`. Write two sentences on what p = 0.250 lets
you conclude and what it does not. Which configured update does no control see, and what signal would?

### 7. The simulated month and the T4 criteria (20 min)

Run `python -m mainlab.report month`. For documentation upkeep, list each failing criterion and the evidence that would
close it. Fill in `templates/maintenance-task-review.md` for one task type.

### 8. ADR-010's table and the workspace audit (20 min)

Run `python -m mainlab.report dst`. Read the three pinned test files and say what each would need. Then run the
workspace audit from `labs/ch03/L3.1-accountable-workspace/solution/`:
`python -m audit.report --policy ../data/policy.json --as-of 2027-07-09 --fail-on high ../../../ch19/L19.1-maintenance-bot/relay-repo`
(0 open, 0 waived).

## Expected evidence

- `evidence/controls.md` and `evidence/demo.md`, each with a paragraph naming the control behind every result.
- Your extra refused approver from step 4, with the code you predicted and the one you got.
- Your two sentences on the replay, and a completed `templates/maintenance-task-review.md`.

## Troubleshooting

- `NotImplementedError: TODO n`: expected until you implement TODO n.
- `ModuleNotFoundError: relay`: run from `starter/` or `solution/`; `mainlab/__init__.py` puts `../relay-repo/src` on the path.
- A sandbox check reports `refused` for legitimate code: you added an import the sandbox refuses (for example `sqlite3`
  or `subprocess`); the lab's checks use only pure-Python modules.
- Results differ from the chapter: check `LAB_TARGET`, then rerun `python scripts/generate_data.py` and
  `git diff data/`; the generated data must not change.
- `UnicodeEncodeError` on Windows: set `PYTHONIOENCODING=utf-8`.

## Known limits

The bot's runner and its scheduled deployment are not built: `.github/workflows/maintenance.yml` names an illustrative
runner, and the lab drives `relay.maintenance` directly. The `relay-maintenance` GitHub App is not created; the code host
is a fake. The sign-in guard metric is not yet in Relay's telemetry or canary configuration (`docs/slo/`,
`deploy/rollout/`, the platform leads' change). The security gate's result in the evidence bundle is a supplied record,
labelled modelled. The sandbox's local layer is Chapter 18's tripwire, not a boundary. Team membership is declared in
the policy, not read from the code host. Two shared files changed with the branch: `deploy/gitops/production.json`'s
`release` field is a version sync that `tests/test_pipeline_config.py` requires, not a deployment, and
`governance/pipeline-guard.json` gains the bot's paths. In a real repository each is a pipeline path and would travel in
its own pull request (PG001).

## Cleanup

The sandbox deletes its temporary folders. Delete `evidence/` contents you do not want to keep.

## Rubric (10 points)

| Points | Criterion |
| ---: | --- |
| 2 | Timeline and controls correct (tests pass), with the reason each pre-release check passed |
| 3 | Worked example correct, with the modelled item explained and an extra refused approver predicted |
| 2 | The three behaviours, each tied to the control that produced it |
| 2 | Replay correct and read honestly; the unseen regression and the signal that would see it |
| 1 | A completed task review and the DST follow-up |

# Lab 19.2 — A Safety and Security Case with Adversarial-Input and Budget-Exhaustion Tests

| | |
| --- | --- |
| Chapter | 19 — Bounded Autonomy: Self-Maintaining Software |
| Type | Stretch |
| Time | 3 hours |
| Cost ceiling | $0. Offline; the model is a script and nothing is installed |
| Requires | Python 3.11+, pytest (`pip install -e ".[dev]"`), and **Lab 19.1's folder beside this one**: the lab runs Relay 4.31.0 from `../L19.1-maintenance-bot/relay-repo/src` |

## Brief

Relay's maintenance bot works at T2, and Chapter 19's release check requires a separately approved safety and security
case before any self-modifying or self-deploying behaviour. In this lab you check a draft case for the bot as it is:
sixteen adversarial records and six long-running scenarios run against Relay's real controls, and each result is bound to
an evidence item. Relay's checker then lists every gap. Your job is to understand each gap and say what would close it.

**About the data.** `data/` is written by `scripts/generate_data.py`. The adversarial records are **labelled, inert
placeholders**: each names the action an attacker's text would ask for, and the lab's scripted model performs that action.
What is tested is whether a control refuses it. No record contains working injection text. Costs in the budget
scenarios are configured.

## What you will practise

- Testing controls with adversarial inputs that are labelled and inert, and requiring each refusal to be audited.
- Testing the stops of a long-running agent: budget, raise, crash and resume, cancellation, repeated hand-backs.
- Binding evidence to results, and telling verified, deployed and modelled evidence apart.
- Reading a case's gaps (weak evidence, open defeaters) as findings, not failures of the tests.

## Folder layout

```
L19.2-safety-security-case/
├── data/                  ← GENERATED: adversarial.json, budget.json, case-draft.json, drills.json, manifest.json
├── scripts/generate_data.py
├── starter/caselab/
│   ├── adversarial.py     ← TODO 1: verdict
│   ├── budget.py          ← TODO 2: run_scenario
│   ├── case.py            ← TODO 3: results
│   ├── harness.py         ← provided: runs one record against Relay's controls
│   └── report.py          ← provided
├── solution/caselab/
├── templates/safety-case-review.md
├── tests/test_caselab.py  ← hand-checkable tests, golden lines, data reproducibility
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. In bash: `LAB_TARGET=solution python -m pytest -q`. In PowerShell:
`$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Always remove the variable afterwards,
or later runs silently grade the solution. Until you finish, failing tests stop with `NotImplementedError`.

## Steps

### 1. Read the case (20 min)

Read Section 19.5 of the chapter, ADR-056, `data/case-draft.json` and the docstring of
`../L19.1-maintenance-bot/relay-repo/src/relay/maintenance/safety_case.py`. For each claim, say which evidence supports it.

### 2. Adversarial inputs: TODO 1 (35 min)

Implement `verdict` in `adversarial.py`, then `cd starter && python -m caselab.report adversarial > ../evidence/adversarial.md`.
On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 ../evidence/adversarial.md`. Which records
need no audit record, and why is their outcome evidence enough? A01 to A03 name paths the task's own file list includes: which rule refuses them, and what does the mutation test in
`tests/test_caselab.py` show? A16 opens a pull request on a three-day-old approval: why is that refused?

### 3. Budget exhaustion and long runs: TODO 2 (45 min)

Implement `run_scenario` in `budget.py`, then `python -m caselab.report budget`. Explain B01's three items, B04's
$0.0200 for one finished item, and B06's single step.

### 4. The case: TODO 3 (30 min)

Implement `results` in `case.py`, then `python -m caselab.report case`. For each of the five problems, say whether it is
a weakness of the bot, of the evidence, or of the case itself.

### 5. Close one gap (30 min)

Pick one problem and close it honestly in a scratch copy of `data/case-draft.json` or `data/drills.json`: add the
evidence that would answer a defeater, or change a drill to the strength it really has. Rerun the case and record what
changed. Do not mark modelled evidence as deployed; say instead what deployment would produce it.

### 6. Review (20 min)

Fill in `templates/safety-case-review.md` as the second approver from `@relay/security` would.

## Expected evidence

- `evidence/adversarial.md`, the budget table and the case report, each with your explanations.
- Your closed gap, with before and after.
- A completed `templates/safety-case-review.md`.

## Troubleshooting

- `ModuleNotFoundError: relay`: Lab 19.1 must sit beside this lab as `../L19.1-maintenance-bot/`.
- `NotImplementedError: TODO n`: expected until you implement TODO n.
- A13 reports something other than `refused`: check that you did not change the sandbox policy in Lab 19.1's copy.
- `UnicodeEncodeError` on Windows: set `PYTHONIOENCODING=utf-8`.

## Known limits

The draft covers the bot at T2 only. Its kill-switch evidence is a test in code, not a drill on a deployed system, and its
rollback evidence is Lab 19.1's configured canary; the checker reports both as too weak, correctly. The checker verifies
structure and the results cited; it cannot tell whether the claims are the right ones. That is the reviewer's job.

## Cleanup

Delete `evidence/` contents you do not want to keep.

## Rubric (10 points)

| Points | Criterion |
| ---: | --- |
| 3 | Adversarial verdicts correct (tests pass), with the audit question answered |
| 3 | Budget scenarios correct, with B01, B04 and B06 explained |
| 2 | Case results correct, each problem classified |
| 2 | One gap closed honestly, and a completed review |

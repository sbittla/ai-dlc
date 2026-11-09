# Lab 10.2 — Failure Injection, Approval Gates and Recovery

| | |
| --- | --- |
| Chapter | 10 — Designing Agentic Systems |
| Type | Stretch |
| Time | 3 hours: 10 minutes of setup and 170 minutes of steps |
| Cost ceiling | $0. Runs locally; no cloud and no model calls |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). No other packages |

## Brief

Lab 10.1 compared designs when nothing went wrong. This lab breaks the spec-to-PR helper on purpose, sixteen ways, and checks that Relay 4.24.0's runtime recovers safely each time. The faults are a process that dies after GitHub answered, a test runner that times out, a model API that fails, a kill switch tripped mid-run, and approvals denied, changed, left to expire or given by the wrong person. Others are a budget that runs out, a duplicate trigger, a file that tries to give the agent new instructions, a steered agent that changes the diff after approval, a transient GitHub error, and a run that outlives its token and ends as `delegation_expired`, waiting for its requester. Every decision is made with the person's own short-lived proof (Chapter 14).

The runtime is Relay's own code, `relay.agents` and `relay.audit`, copied from Lab 10.1's reference solution into `data/relay-4.24.0/` by `scripts/generate_data.py`. **The model and GitHub are simulated.** The model follows a fixed plan with fixed token counts, so every drill can be followed by hand.

## What you will practise

- **Making an external effect safe to repeat**: look before you create.
- **Resuming a run in a new process** without resetting its budget or repeating its effects.
- **Approval gates as code**: bound to exact arguments, expiring, decided only by people, and by someone other than the requester for a budget raise.
- **Writing drills** that state the outcome a control must produce, and judging them mechanically.

## Folder layout

```
L10.2-failure-injection-approval-gates/
├── data/
│   ├── relay-4.24.0/src/relay/  ← GENERATED: relay.agents and relay.audit from Lab 10.1's solution
│   └── faults.json              ← input: the sixteen drills, the decisions people make, the expected outcomes
├── scripts/generate_data.py
├── starter/faultlab/
│   ├── github.py                ← TODO 1: open_pull_request
│   ├── recover.py               ← TODO 2: resume (start is provided)
│   ├── drills.py                ← TODO 3: verdict (run_drill is provided)
│   └── helper.py, report.py     ← provided: the resumable helper, its fault points, the report
├── solution/                    ← reference solution (instructors; read only after finishing)
├── templates/recovery-record.md
├── tests/                       ← test_github.py, test_recover.py, test_drills.py (hand-checkable), test_golden.py
└── evidence/                    ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it. Until you finish, every failing test stops with `NotImplementedError`.

On Windows PowerShell 5.1, `>` writes UTF-16. Where a step redirects a report to a file, use `| Out-File -Encoding utf8 <file>` instead. PowerShell 7 writes UTF-8.

## Steps

### 0. Set up (10 min)

Run `pip install -e ".[dev]"` in this folder, then `python -m pytest -q` once.

### 1. Read the helper and the drills (20 min)

Read `starter/faultlab/helper.py` and `data/faults.json`. For D02, D03 and D05, write down where the fault fires, which journal entry exists at that moment, and what you expect resuming to do.

### 2. A pull request that is safe to open twice (25 min)

Implement `open_pull_request` in `starter/faultlab/github.py`. Then read `HELPER_TOOLS["open_pull_request"]` in `data/relay-4.24.0/src/relay/agents/tools.py`: why may its contract say `idempotent=True` only once your handler looks first?

```bash
python -m pytest -q tests/test_github.py
```

### 3. Resume (40 min)

Implement `resume` in `starter/faultlab/recover.py`. What would go wrong in D05 if you did not restore the meter? In D04, if you did not rebuild the history?

```bash
python -m pytest -q tests/test_recover.py
```

### 4. Judge the drills (15 min)

Implement `verdict` in `starter/faultlab/drills.py`.

### 5. Run every drill (15 min)

```bash
python -m pytest -q
cd starter
python -m faultlab.report > ../evidence/drills.md
cd ..
```

Explain the last line of the report: what happened to D02 with a handler that does not look first?

### 6. Change one control and watch a drill (30 min)

Pick one, change it in a scratch copy of `data/relay-4.24.0/` (then run `python scripts/generate_data.py` to restore it), and record which drill fails and how:
- mark `edit_file` as `idempotent=True` in `tools.py` (D03);
- let `ApprovalGate.decide` accept the requester for `another_person` (D10);
- drop `"diff_sha256"` from `open_pull_request`'s `derived` fields and make it a parameter again, so the agent reports its own diff (D13);
- remove the `not_the_requester` check from `ApprovalGate.decide` (D14).
For the first, argue whether the change is right: when is rewriting a whole file safe to repeat?

### 7. Recovery record (25 min)

Complete `templates/recovery-record.md` as `evidence/recovery-record.md`: one row per drill, with the control that produced the outcome and the person who acts next.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/drills.md` | The report, with step 5's explanation |
| `evidence/control-change.md` | Step 6: the change, the failing drill and your argument |
| `evidence/recovery-record.md` | Every drill, its control and the next person |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> D02: GitHub created pull request 5100, then the process died before the journal recorded the step, so the step was still `started`. On resume the boundary found the started step; the contract declares an idempotent handler, so it ran it again, and the handler found 5100 on the branch and created nothing. With a handler that creates without looking, the same drill opens two pull requests. The approval was not asked for twice, because it was bound to the same arguments and was already approved.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| D02 opens two pull requests | `open_pull_request` creates before it looks, or does not ignore closed pull requests. |
| D05 or D10 reports `budget_carried: False` | `resume` did not restore the meter from the checkpoint. |
| D04 never stops | `resume` did not rebuild the history, so the repeated-failure count starts again. |
| D06 resumes | `resume` must refuse a run whose status is final, including `revoked`. |
| `PermissionError` on a `.db` file on Windows | A store was left open; `run_drill` closes every process's store, so check your own scratch code. |

## Cleanup

Nothing to clean up. Drills write their run stores to a temporary folder that is removed afterwards.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Idempotent pull request | 2 | `tests/test_github.py` passes and step 2's question is answered |
| Resume | 3 | `tests/test_recover.py` passes and step 3's two questions are answered |
| Drills | 2 | All sixteen pass and step 5 explains the blind handler |
| Control change | 2 | One change made, its failing drill named, and the argument is sound |
| Recovery record | 1 | Every drill has a control and a next person |

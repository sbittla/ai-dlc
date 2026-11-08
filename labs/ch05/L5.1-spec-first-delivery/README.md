# Lab 5.1 — Spec-First Feature Delivery

| | |
| --- | --- |
| Chapter | 5 — Specification-Driven Development |
| Type | Core (Builder, Platform) |
| Time | 4 hours |
| Cost ceiling | $0. Runs locally; no cloud and no model calls. If you ask a coding agent to help, it runs under your own subscription |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

In November three coding agents built Relay's escalation evaluator from three slightly different prompts, and produced three designs that cannot read each other's documents. Chapter 5 tells the story. PRD v1.0 from Chapter 4 was approved on 19 November; nobody had written down the interface between it and the code.

You will deliver the first slice of escalation rules spec-first: rule validation and rule evaluation, nothing else. The approved PRD is in `data/prd-v1.md`. Relay 4.17.2, copied from Chapter 3, is in `starter/relay-repo/`, with the new package `src/relay/escalation/`, its acceptance tests and a spec package scaffold in `specs/001-escalation-rules/`.

You have four jobs.

1. **Build a small spec checker** that CI can run on every spec change: required sections, a test for every criterion with the criterion's ID, tasks linked to criteria, autonomy tiers within Chapter 1's caps, and a classification for every contract field.
2. **Complete the spec package**: data rules, four security constraints, a coverage decision for each of the 12 criteria in the slice, and tasks T04–T09.
3. **Implement the slice** so that the acceptance tests, named after their criteria, pass, and the documents it returns conform to the contract.
4. **Get the spec approved** by a product owner, a tech lead and a security reviewer, with a review record that says what the checks cannot see.

This release is Relay **4.18.0**. Chapter 8 builds the full escalation engine test-first from this spec, starting from this code.

## Tracks

| Step | Builder | Platform |
| --- | ---: | ---: |
| 1. Read the PRD slice, the incident and the scaffold | 20 min | 20 min |
| 2. Implement the spec checker | 50 min | 50 min |
| 3. Check the scaffold and the draft task list | 15 min | 15 min |
| 4. Complete the spec package | 60 min | 60 min |
| 5. Generate and review the task graph | 20 min | 20 min |
| 6. Implement the slice (Builder) or wire the gates (Platform) | 55 min | 55 min |
| 7. Contract and gate | 10 min | 10 min |
| 8. Review and approval | 10 min | 10 min |
| **Total** | **240 min** | **240 min** |

- **Builder:** do every step; step 6 is the slice's code.
- **Platform:** in step 6, copy the reference slice instead of writing it (`cp ../solution/relay-repo/src/relay/escalation/rules.py ../solution/relay-repo/src/relay/escalation/evaluate.py relay-repo/src/relay/escalation/` from `starter/`). Spend the time on step 6P: the CI wiring that makes the spec checker and the contract tests required. The rubric's 2 points for the slice are given for that wiring.

## What you will practise

- Writing a **versioned spec package** before code: goals, non-goals, actors, behaviour, NFRs, contracts, data rules with classification, security constraints and acceptance criteria.
- Deciding **what a slice covers**, and saying which part of a criterion it defers.
- Turning a spec into **small, dependency-aware, risk-labelled tasks**, each with an autonomy tier, and checking the untrusted-input cap mechanically.
- **Executable contracts**: a JSON Schema the implementation's documents are validated against, and policy tests generated from the spec's security constraints.
- Keeping a change **disjoint**: Relay 4.18.0 adds files under three paths and modifies four, and a test proves it.

## Folder layout

```
L5.1-spec-first-delivery/
├── data/
│   ├── prd-v1.md                  ← PRD v1.0, byte-identical to Lab 4.1's (input; not generated)
│   ├── relay-4.17.2-manifest.json ← SHA-256 of every 4.17.2 file (input): proves what 4.18.0 changed
│   ├── spec-v1/                   ← the approved spec package: the reference answer (read it only after step 5)
│   ├── spec-scaffold/             ← GENERATED: the package with your parts removed (29 findings, 26 blocking)
│   ├── tasks-draft.md             ← GENERATED: a task list an assistant drafted, unedited (11 findings)
│   └── incident/                  ← GENERATED: what three agents built from three prompts
├── scripts/generate_data.py       ← writes the GENERATED files (deterministic; byte-identical on every platform)
├── starter/
│   ├── speccheck/
│   │   ├── core.py                ← provided: Finding, the 29-check catalogue, the gate policy
│   │   ├── spec.py                ← provided: parses spec.md, tasks.md, the contract and the PRD
│   │   ├── repo.py                ← provided: finds tests and the criterion IDs their names carry
│   │   ├── checks.py              ← TODO: 5 functions; the other checks are provided
│   │   ├── plan.py                ← provided: waves, longest chain, Mermaid, trace matrix
│   │   ├── incident.py            ← provided: the three designs against the contract
│   │   └── report.py              ← provided: the report, --details, --plan, --gate
│   └── relay-repo/                ← Relay 4.18.0 in progress
│       ├── specs/001-escalation-rules/   ← spec.md and tasks.md to complete; contracts/ is complete
│       ├── src/relay/escalation/  ← TODO: validate_rule (rules.py) and evaluate (evaluate.py)
│       └── tests/escalation/      ← provided: acceptance, contract and policy tests (30)
├── solution/                      ← reference solution (instructors; read only after finishing)
├── templates/spec-review.md
├── tests/                         ← test_checks.py (hand-checkable), test_slice.py, test_golden.py
└── evidence/                      ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's folder.

Until you finish, every failing test stops with `NotImplementedError`. Relay's own suite runs too: `cd starter/relay-repo && python -m pytest -q`.

## Steps

### 1. Read the PRD slice, the incident and the scaffold (20 min)

Read PRD v1.0's requirements ESC-R01 to ESC-R08 and ESC-N01, N05, N06 and N07, with their criteria. Then run the incident report and read the three designs:

```bash
cd starter
python -m speccheck.incident --incident ../data/incident --contract relay-repo/specs/001-escalation-rules/contracts/escalation-rules.schema.json
```

Now read `relay-repo/specs/001-escalation-rules/spec.md` and the contract next to it. Which of the incident's three disagreements does the contract settle? Which does only the spec's prose settle?

### 2. Implement the spec checker (50 min)

Implement the five TODO functions in `starter/speccheck/checks.py`. Each docstring is the specification; `tests/test_checks.py` checks each on inputs you can verify by hand.

| Function | What it decides |
| --- | --- |
| `check_sections` | Are the nine required sections present, and none left empty or marked TO COMPLETE? |
| `check_tests` | Does every criterion have a test carrying its ID, and does every such test name a criterion of this spec? |
| `check_task_links` | Does every task check something the spec defines, and is every criterion and constraint checked by a task? |
| `check_tiers` | Has every task a tier, within the untrusted-input cap (T2) and never T4 if sensitive? |
| `check_classification` | Has every contract field a data classification from the four allowed? |

```bash
python -m pytest -q tests/test_checks.py
```

### 3. Check the scaffold and the draft task list (15 min)

```bash
cd starter
python -m speccheck.report --prd ../data/prd-v1.md --tests relay-repo/tests --spec relay-repo/specs/001-escalation-rules --spec ../data/spec-scaffold --tasks - --tasks ../data/tasks-draft.md --details > ../evidence/scaffold-check.md
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

The second column checks the assistant's draft task list against the scaffold. Pick its three most harmful findings. Look hard at T05 and T06: what did the drafting assistant read that made it plan an SMS channel?

### 4. Complete the spec package (60 min)

In `starter/relay-repo/specs/001-escalation-rules/spec.md`:

- **Data rules:** one row per contract field (all 20), plus `Task.title`, `User.name`, `User.email` and `EscalationState.suggested_priority`. Use Public, Internal, Confidential or Restricted. List `Evaluation` and `StepDecision` as outbound; nothing in them may be Confidential.
- **Security constraints:** SEC-02 to SEC-05, each with Source:, Checks: and Statement:. SEC-03, SEC-04 and SEC-05 name the policy tests that already exist (`test_SEC03`, `test_SEC04`, `test_SEC05`).
- **Coverage:** for each of the 12 criteria, `full` or `partial`. A criterion is `full` only if this slice's code can observe its whole Then clause, read with the spec's "Terms at this boundary". Every `partial` needs a Deferred: line naming what is deferred and to which later stage.

Do not edit a criterion's text: the checker compares it word for word with the PRD (SP021). If a criterion is wrong, the fix is a change to the PRD first.

### 5. Generate and review the task graph (20 min)

Write tasks T04 onwards in `tasks.md`, then:

```bash
cd starter
python -m speccheck.report --prd ../data/prd-v1.md --tests relay-repo/tests --spec relay-repo/specs/001-escalation-rules --plan
```

Read the waves and the trace matrix. Which tasks can run in parallel? Which task reads untrusted input, and what caps its tier? Only now compare your package with `data/spec-v1/`.

### 6. Implement the slice (Builder, 55 min)

Implement `validate_rule` in `relay-repo/src/relay/escalation/rules.py` and `evaluate` in `evaluate.py`. Their docstrings follow the spec's Behavior section exactly. Work task by task in the order of your waves, and run the criterion's tests as you go:

```bash
cd starter/relay-repo
python -m pytest -q tests/escalation -k "ESC_AC08 or ESC_AC09"
python -m pytest -q && python tools/lint.py
```

If you use a coding agent, give it one task at a time: the task's block from `tasks.md`, the spec, and the instruction to change only the task's Files. Run it at the tier the task names.

### 6P. Wire the gates (Platform, 55 min)

Write the change as the platform team's separate pull request, in `evidence/`, not in `relay-repo/` (the slice's pull request must not touch `.github/` or `governance/`, and `tests/test_slice.py` checks that it does not). Write `evidence/ci-spec-check.yml`: a `spec-check` job that runs the checker with `--gate` and the escalation tests. Write `evidence/branch-protection.json`: Relay's file with `spec-check` added to the required status checks. Check that `relay-repo/.github/CODEOWNERS` gives `specs/` to the product team and `rules.py` to security. In `evidence/spec-review.md` section 7, say how a spec change reaches `Status: approved`, and why the checker must come from a pinned copy outside the pull request it checks.

### 7. Contract and gate (10 min)

```bash
cd starter
python -m speccheck.report --prd ../data/prd-v1.md --tests relay-repo/tests --spec relay-repo/specs/001-escalation-rules --gate; echo "exit $?"
cd .. && python -m pytest -q
```

In PowerShell, use `echo "exit $LASTEXITCODE"`. The gate blocks on every check except three warnings (SP011, SP031, SP044). `tests/test_slice.py` also checks that your Relay changes stay inside the slice: only four 4.17.2 files may change.

### 8. Review and approval (10 min)

Complete `templates/spec-review.md` in `evidence/`. Ask three colleagues, or your instructor, to act as product owner, tech lead and security reviewer: their names go in the header and in `Approved by`. The spec's `Risk: high` makes the security reviewer's approval required (SP080). SP080 checks the record only; in a real repository each approval is a required code-owner review on the pull request that sets `Status: approved`.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/scaffold-check.md` | The checker's report on the scaffold and the draft task list, with details |
| `relay-repo/specs/001-escalation-rules/` (in `starter/`) | The completed, approved spec package: no blocking findings |
| `evidence/spec-review.md` | Every template section completed |
| `evidence/ci-spec-check.yml`, `evidence/branch-protection.json` | Platform track only: the gate job and the required-check change |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The scaffold had 29 open findings, 26 of them blocking. The assistant's draft task list had 11: one critical, T05 reading the injection ticket TK32 at T3 above the T2 cap, and a T4 task that would have let an agent merge permission code unreviewed. Its T06 plans an SMS channel and checks no criterion; the assistant took "SMS was agreed with the vendor" from INT-1's pasted text, which Chapter 4 flagged. Our package covers 12 of PRD v1.0's 31 criteria, 4 of them partly: ESC-AC08's delivery, ESC-AC18's display, ESC-AC24's audit entry and ESC-AC27's email and webhook payloads are deferred to Chapter 8 or Chapter 6. The task graph has 9 tasks in 4 waves, all at T2. The checks cannot tell us that a test asserts all of its criterion: ESC-AC10's test must check that the message names the range, and we read each test against its criterion before approval. The product owner, tech lead and security reviewer approved in a recorded review.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| SP021 on a criterion you did not change | Curly quotes or a changed space. The criterion must match the PRD exactly; copy it from `data/prd-v1.md`. |
| SP030 for a criterion that has a test | The test's name must start `test_ESC_AC08` and continue with `_` or end there. `test_esc_ac08` and `test_ESC_AC08x` do not count. |
| SP060 on every field | Field names in the data rules table must be in backticks, as `` `Rule.rule_id` ``. |
| SP062 after you added a field | An outbound document's field is Confidential or Restricted. Remove the field, or move the document out of Outbound if it never leaves Relay. |
| `test_SEC04` stops with NotImplementedError | The Data rules table is still empty. |
| `test_changes_to_relay_stay_inside_the_escalation_slice` fails | You changed a 4.17.2 file other than the four listed, or added a file outside `src/relay/escalation/`, `tests/escalation/` and `specs/001-escalation-rules/`. |
| SP043 dependency cycle | A task depends, directly or through others, on itself. `--plan` refuses to draw a cyclic graph. |

## Cleanup

Nothing to clean up. If an agent worked in `relay-repo/`, check `git status` for files outside the slice.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Checker correct | 3 | All `tests/test_checks.py` tests pass against `starter/` |
| Spec package | 3 | No blocking findings; every field classified with a reason for each Confidential one; four security constraints, each with a source and an executable check; every partial criterion names what it defers |
| Tasks and tiers | 1 | Small tasks in waves; the untrusted-input task at T2 or below, with the reason |
| Slice (Builder) or gates (Platform) | 2 | Builder: the full suite and lint pass, and only the allowed files changed. Platform: the spec gate is a required check and spec approval needs the product owner's code-owner review |
| Review record | 1 | Names three things the checks cannot see, with the human step for each, and approvers who are neither the author nor an agent |

# Lab 9.1 — Feature from Approved Spec to Reviewed Pull Request

| | |
| --- | --- |
| Chapter | 9 — Agent-Assisted Implementation, Review and Modernization |
| Type | Core |
| Time | 5 hours, tight: the steps take 290 minutes after 10 minutes of setup. Steps 7 and 8 can be finished afterwards |
| Cost ceiling | $0. Runs locally; no cloud and no model calls. The optional live review (step 8) calls a Claude model under your own key and refuses any call estimated above $0.50 |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). No other packages. Live review only: `pip install -e ".[live]"` |

## Brief

On 8 December 2026 a 4,067-line pull request written by a coding agent was approved after a ten-minute review, and its migration lost Relay users' notification preferences (Chapter 9, opening incident). `data/incident-pr.json` records it. This lab takes the next feature the other way: from an approved spec change to a series of small pull requests, each one checked before a person reviews it.

The feature is rule deletion with ESC-AC25's notices, from spec ESC-SPEC-1 1.2.0. It needs a schema migration (the audit table's CHECK constraint must accept a new outcome), an engine change, a new HTTP route with its OpenAPI operation, and docs. Before writing any code you check what a simulated agent claimed the change would touch, against the source. Then you implement the deletion against approved tests, build the pull-request check, and measure all nine pull requests of Relay **4.22.0**. The worker's escalation pass, the route and the docs are provided; you implement the deletion itself.

## What you will practise

- **Verifying an agent's claims** about a codebase against the source and tests, before acting on them.
- **Implementing from a spec in small increments**: approved tests first, then code, in a pull request a person can review.
- **Reviewing a migration** for the ways it can lose data, and proving a copy before dropping anything.
- **Checking a pull request before review**: size limits, tests-first commits, migrations, routes and docs.
- **Writing a pull request a reviewer can trust**: every claim with its evidence, and an author who can explain every line.

## Folder layout

```
L9.1-spec-to-reviewed-pr/
├── data/
│   ├── relay-4.21.0/          ← GENERATED: canonical Relay 4.21.0's src, tests, specs, docs; the base
│   ├── prd-v1.1.md            ← GENERATED: PRD v1.1, copied from Lab 8.1 (spec 1.2.0 is derived from it)
│   ├── incident-pr.json       ← input: the opening incident's pull request, reconstructed
│   ├── agent-claims.json      ← input: a SIMULATED agent's eight impact-analysis claims
│   └── pr-plan.json           ← input: Relay 4.22.0's nine pull requests, their commits and reviewers
├── scripts/generate_data.py   ← writes the GENERATED files (deterministic)
├── starter/
│   ├── prkit/
│   │   ├── prcheck.py         ← TODO: check_pr (PR01 to PR10)
│   │   ├── claims.py          ← TODO: check_values, verify_claim
│   │   ├── diffs.py, codeowners.py, series.py, report.py   ← provided
│   │   └── live.py            ← provided, optional: a Claude model reviews one pull request
│   └── relay-repo/            ← Relay 4.22.0 in progress
│       ├── specs/001-escalation-rules/   ← spec 1.2.0 (B8, SEC-08, SEC-09), tasks T21 to T25
│       ├── docs/adr/          ← ADR-016 to ADR-019
│       └── src/relay/escalation/   ← TODO: EscalationStore.delete_rule (store.py), delete_rule (engine.py)
├── solution/                  ← reference solution (instructors; read only after finishing)
├── templates/                 ← review-checklist.md, pr-description.md, review-record.md
├── tests/                     ← test_prcheck.py, test_claims.py (hand-checkable), test_relay.py, test_rollback.py, test_golden.py
└── evidence/                  ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's folder.

Until you finish, every failing test stops with `NotImplementedError`. Relay's own suite runs too: `cd starter/relay-repo` and `python -m pytest -q`.

On Windows PowerShell 5.1, `>` writes UTF-16. Where a step redirects a report to a file, use `| Out-File -Encoding utf8 <file>` instead. PowerShell 7 writes UTF-8.

## Steps

### 0. Set up (10 min)

Create a virtual environment if you have not, run `pip install -e ".[dev]"` in this folder, and run `python -m pytest -q` once to see the starting state.

### 1. Read the change and the incident (15 min)

Read `starter/relay-repo/specs/001-escalation-rules/spec.md` sections B8, "Terms at this boundary", SEC-08 and SEC-09, then ADR-016 and ADR-019. Then read `data/incident-pr.json`. Write down three things the incident's reviewer could not have checked in ten minutes.

### 2. Check the agent's claims (45 min)

`data/agent-claims.json` holds eight claims a simulated agent made about Relay 4.21.0 before the work started. Implement `check_values` and `verify_claim` in `starter/prkit/claims.py`; the docstring's table is the specification, and the other helpers are provided.

```bash
python -m pytest -q tests/test_claims.py
cd starter
python -m prkit.report claims > ../evidence/claims.md
cd ..
```

For each claim that does not hold, write in `evidence/claims.md` what would have gone wrong if you had believed it.

### 3. Review the migration (30 min)

Read `starter/relay-repo/src/relay/escalation/migrations.py` and `tests/escalation/test_escalation_migrations.py` with section D of `templates/review-checklist.md`. In `evidence/migration-review.md`, answer: what does the proof compare, and why not the column list the copy used? What happens if two processes open the database at once? What does the downgrade refuse, and why?

### 4. Implement deletion against the approved tests (70 min)

Implement `EscalationStore.delete_rule` in `store.py` and `delete_rule` in `engine.py`. The approved tests are `tests/escalation/test_escalation_deletion.py` and `tests/test_service_rule_deletion.py`; do not change them. If you use a coding agent, give it spec section B8, task T23 and the tests, and tell it the tests are fixed.

```bash
cd starter/relay-repo
python -m pytest -q tests/escalation/test_escalation_deletion.py
python -m pytest -q
python tools/lint.py
cd ../..
```

The route (`src/relay/service/escalation_routes.py`) is provided. Read it against B7 and B8. Why does it answer 404 for a project the caller cannot view before it checks the role, and write no audit entry then? Why does it check the role and the rule itself before calling the engine? Then read `tests/test_rollback.py`: what happens to a deleted rule if the code is rolled back to 4.21.0?

### 5. Build the pull-request check (55 min)

Implement `check_pr` in `starter/prkit/prcheck.py`, PR01 to PR10 in the order of the docstring's table. `tests/test_prcheck.py` checks each rule on records small enough to work out by hand.

```bash
python -m pytest -q tests/test_prcheck.py
```

### 6. Measure the incident and the series (20 min)

```bash
cd starter
python -m prkit.report incident > ../evidence/incident.md
python -m prkit.report series > ../evidence/series.md
cd ..
```

Answer in `evidence/series.md`: which findings would have stopped the incident's pull request before review? Which pull request in the series is largest, and is it still reviewable at the rate recorded? Why does PR-0, the review policy, merge before everything else, and who reviewed it?

### 7. Write a pull-request description (30 min)

Using `templates/pr-description.md`, write the description of PR-5 (task T23) in `evidence/pr-5.md`. Every claim needs its file and line. Include the summary-link fix that impact analysis found.

### 8. Review record, and optionally an AI second reader (25 min)

Review PR-5 with `templates/review-checklist.md` and complete `templates/review-record.md` in `evidence/`. Then record that the pre-review check is not yet a required status check in `governance/branch-protection.json`: add `pr-check` to a copy in `evidence/`, as Lab 8.1's Platform track did, and say who must approve the real change. Optionally, run the live review and compare it with your checklist: `RELAY_LAB_LIVE=1 python -m prkit.report live-review --pr PR-5` from `starter/` (bash), or `$env:RELAY_LAB_LIVE="1"; python -m prkit.report live-review --pr PR-5; Remove-Item Env:RELAY_LAB_LIVE` (PowerShell). Record which items it got right, which it missed, and which it asserted without quoting a line.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/claims.md` | The claims report, and for each claim that does not hold, its consequence |
| `evidence/migration-review.md` | Answers to step 3's three questions, with file and line |
| `evidence/incident.md`, `evidence/series.md` | The two reports, with step 6's answers |
| `evidence/pr-5.md` | A description in the template's shape, every claim with evidence |
| `evidence/review-record.md` | Every section, by a reviewer who is neither the author nor an agent |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> Four of the agent's eight claims did not hold. C2 said only the GET route looks a rule up by ID; engine.py does too, at lines 67 and 245, and the second is the hour's summary, which would have linked a deleted rule's held emails to project 0. C4 said the audit table accepts any outcome; store.py line 36 constrains it to 'saved' and 'refused', so a deletion needs a table rebuild, which is the migration in T21. The incident's pull request fails four blocking checks before anyone reads it: 2,602 lines outside tests, six existing tests changed in the code commit, no tests-first commit, and a migration with no migration test.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `relay-repo stops with NotImplementedError` | Step 4 is not finished. |
| A deletion test fails with 500 instead of the expected status | The engine raised; run `tests/escalation/test_escalation_deletion.py` first, which shows the real error. |
| `PR10` on a pull request | Every reviewer opened it or wrote one of its commits; an agent's commits count as the person who ran it. |
| `PR02` on a pull request you think is fine | A commit that changes `src/` also changes a test file that existed before the pull request. Put test changes in the tests-only commit. |
| `PR04` on a change with no migration | An added line contains `DROP TABLE` or `ALTER TABLE`, or a path contains "migrat". Add a migration test, or move the SQL. |
| `test_every_change_since_4_21_0...` fails | A file changed in `relay-repo` that `data/pr-plan.json` does not assign, or a forbidden path (`infra/`, `deploy/`, `sharedlimit.py`, `wsgi.py`, `governance/`) changed. |
| Golden tests fail after you edited `data/` | Regenerate with `python scripts/generate_data.py`; inputs written by hand are not regenerated. |

## Cleanup

Nothing to clean up. The release report runs pytest's collection in `solution/relay-repo` and writes nothing. If you ran Relay's service or worker by hand, delete the `relay.db` files you created.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Claims checked | 2 | All eight verdicts match, and each false claim's consequence is named with file and line |
| Migration reviewed | 1 | The three questions answered from the code, not the docstring |
| Deletion implemented | 3 | Relay's suite and lint pass, the approved tests unchanged |
| Pull-request check | 2 | `tests/test_prcheck.py` passes, and step 6's answers cite the findings |
| Description and review | 2 | Every claim in `pr-5.md` has evidence; the review record answers every checklist item and asks the author a question |

# Lab 10.1 — One Task, Three Designs: Workflow, Single Agent and Multi-Agent, Compared

| | |
| --- | --- |
| Chapter | 10 — Designing Agentic Systems |
| Type | Core |
| Time | 5 hours: 10 minutes of setup and 280 minutes of steps. The optional step 8 adds 15 minutes |
| Cost ceiling | $0. Runs locally; no cloud and no model calls. The optional live step calls a Claude model under your own key and refuses any call estimated above $0.50 |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). No other packages. Live step only: `pip install -e ".[live]"` |

## Brief

On Thursday 14 January 2027 a five-agent prototype of Relay's spec-to-PR helper looped for six hours on one task and spent about $1,800 (Chapter 10, opening incident). `data/incident/pipeline.json` reconstructs it. In this lab you replay that run, then build the helper's controls and compare four designs of the same helper on 120 tasks: a deterministic workflow, a single agent, a supervisor with four agents, and a routed design that runs the agent only when the workflow fails.

Every design runs on Relay **4.24.0**'s agent runtime, `relay-repo/src/relay/agents/`: budgets and stopping conditions, typed tool contracts and the tool-call boundary, resumable run state and approval gates, under the agent identities and audit trail of Chapter 14. Those are real code with real tests. **The model is simulated**: `agentlab/sim.py` plays a model called `sim-large` whose behaviour is configured in `data/simulator.json`. The lab measures how each design's structure turns the same configured behaviour into outcomes, cost and latency. It does not measure any real model.

## What you will practise

- **Stopping an agent with code**: budgets, a repeated-failure rule and a stall rule, checked before every step.
- **Building the deterministic alternative first**, and measuring what an agent adds to it.
- **Comparing designs fairly**: the same tasks and draws, a dev split for tuning and a held-out split for deciding, paired intervals that resample families, and McNemar's test beside them.
- **Reading trajectories**: refused calls, repeated reads, approvals and policy compliance from the audit trail.
- **Writing a design record** that says why each agent exists instead of deterministic code.

## Folder layout

```
L10.1-workflow-agent-multiagent/
├── data/
│   ├── tasks.jsonl            ← GENERATED: 120 tasks in 40 families (30 dev, 90 held-out)
│   ├── simulator.json         ← input: sim-large's configured behaviour, token sizes, latencies
│   ├── designs.json           ← input: each design's budget (from step 6) and stop rules; the gate policy
│   ├── registry.json          ← input: the lab's agent registry (the helper plus five multi-agent identities)
│   └── incident/pipeline.json ← input: the incident's five-agent pipeline
├── scripts/generate_data.py   ← writes tasks.jsonl from canonical Relay 4.23.0's file sizes (deterministic)
├── starter/
│   ├── relay-repo/            ← Relay 4.24.0 in progress
│   │   └── src/relay/agents/  ← TODO 1: Meter.check and Meter.admit (budget.py); TODO 2: stop_reason (loop.py)
│   └── agentlab/
│       ├── designs.py         ← TODO 3: run_workflow; the other three designs are provided
│       ├── compare.py         ← TODO 4: compare; the gate rule is provided
│       └── sim.py, world.py, runtime.py, evaluate.py, calibrate.py, incident.py, report.py, live.py ← provided
├── solution/                  ← reference solution (instructors; read only after finishing)
├── templates/design-record.md
├── tests/                     ← hand-checkable tests for each TODO, test_relay.py, test_golden.py
└── evidence/                  ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's folder.

Until you finish, every failing test stops with `NotImplementedError`. Relay's own suite runs too: `cd starter/relay-repo` and `python -m pytest -q`.

On Windows PowerShell 5.1, `>` writes UTF-16. Where a step redirects a report to a file, use `| Out-File -Encoding utf8 <file>` instead. PowerShell 7 writes UTF-8.

## Steps

### 0. Set up (10 min)

Create a virtual environment if you have not, run `pip install -e ".[dev]"` in this folder, and run `python -m pytest -q` once to see the starting state.

### 1. Replay the incident (25 min)

Read `data/incident/pipeline.json` and `starter/agentlab/incident.py`. The replay of the run as it happened needs none of your TODOs:

```bash
cd starter
python -c "from agentlab.incident import replay; r = replay('none'); print(r.reason, r.calls, round(r.usd, 2))"
cd ..
```

In `evidence/incident.md`, explain why the cost per round grew until round 81 and then stayed flat, and why prompt caching saved nothing.

### 2. Budgets and stopping conditions (50 min)

Implement `Meter.check` and `Meter.admit` in `starter/relay-repo/src/relay/agents/budget.py`, and `stop_reason` in `starter/relay-repo/src/relay/agents/loop.py`. The docstrings are the specification.

```bash
python -m pytest -q tests/test_budget_and_stop.py
cd starter/relay-repo
python -m pytest -q
python tools/lint.py
cd ../..
cd starter
python -m agentlab.report incident > ../evidence/incident-report.md
cd ..
```

Why does `admit` use an upper estimate rather than the call's real cost? What would go wrong if `check` used `>` instead of `>=`?

### 3. The deterministic workflow (60 min)

Implement `run_workflow` in `starter/agentlab/designs.py`, following its docstring step by step. `tests/test_workflow.py` works one task through by hand, including its cost. Read `run_single` and `run_multi` beside it: what does each agent decide that your code decides in the workflow?

```bash
python -m pytest -q tests/test_workflow.py
```

### 4. Run the four designs and read their trajectories (30 min)

```bash
cd starter
python -m agentlab.report trajectory --split dev > ../evidence/trajectory-dev.md
cd ..
```

Pick one single-agent run and one multi-agent run of the same task (`agentlab.evaluate.evaluate("dev")` returns every record). Which calls did the boundary refuse, and why? Why does the multi-agent design read the same files so many more times?

### 5. Compare the designs (45 min)

Implement `compare` in `starter/agentlab/compare.py`. `tests/test_compare.py` checks it on 24 hand-made runs.

```bash
python -m pytest -q tests/test_compare.py
cd starter
python -m agentlab.report compare --split dev > ../evidence/compare-dev.md
python -m agentlab.report paired --split dev > ../evidence/paired-dev.md
cd ..
```

Decide on dev only what dev may decide: budgets and design changes. Then run the held-out split once:

```bash
cd starter
python -m agentlab.report budgets > ../evidence/budgets.md
python -m agentlab.report compare --split heldout > ../evidence/compare-heldout.md
python -m agentlab.report paired --split heldout > ../evidence/paired-heldout.md
python -m agentlab.report slices --split heldout > ../evidence/slices-heldout.md
cd ..
python -m pytest -q
```

### 6. The design record (40 min)

Complete `templates/design-record.md` as `evidence/design-record.md`. For each step of the helper, say whether it is deterministic code, a single model call or an agent, and cite the report row that justifies it. For the routed design, say what the bootstrap interval and McNemar's test each say about success and about wrong pull requests, why they can disagree here, and what the power line of the paired report means for that. Say whether the dev split showed the same.

### 7. Tool contracts and identities (30 min)

Read `relay-repo/src/relay/agents/tools.py`, `boundary.py` and ADR-025. In `evidence/tools-review.md`, list each tool's effect, scope and approval, and answer: which check stops an agent whose kill switch was tripped, and on which call? Why can the multi-agent design not share one identity? Which tool would you add for the incident's reviewer to hand a conflict to a person, and what contract would it have?

### 8. Optional: one real call (15 min)

`RELAY_LAB_LIVE=1 python -m agentlab.report live --task HT-031` from `starter/` (bash), or `$env:RELAY_LAB_LIVE="1"; python -m agentlab.report live --task HT-031; Remove-Item Env:RELAY_LAB_LIVE` (PowerShell). Compare its token counts and latency with `data/simulator.json`'s assumptions, and record the difference.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/incident.md`, `evidence/incident-report.md` | The replay report, with step 1's explanation |
| `evidence/trajectory-dev.md` | The report, with step 4's answers |
| `evidence/compare-*.md`, `evidence/paired-*.md`, `evidence/slices-heldout.md`, `evidence/budgets.md` | The reports from step 5 |
| `evidence/design-record.md` | Every section, with a reviewer who is not the author |
| `evidence/tools-review.md` | Step 7's table and answers |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The workflow fails the gate: on held-out it is 5.9 points behind the single agent, and its interval (−10.0 to −2.6) cannot rule out a loss beyond the 5-point margin. The loss is on cross-file tasks, 6 of 21 against 9 of 21, where the file it needs is not listed and no listed file imports it. The routed design's bootstrap interval (+0.7 to +7.8) excludes zero, but McNemar on majority outcomes (b = 1, c = 4, p = 0.375) does not, and the shared draws narrow the interval: at a 5.6% disagreement rate, 173 tasks would be needed to detect 5 points. Its wrong-PR advantage is run-level only (−4.1, −8.1 to −0.4; by majority b = 1, c = 2), and dev showed the opposite. We chose it for the pilot because the agent runs on a third of the runs, and accepted 18.8% more cost per run; the live rerun decides.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Everything stops with `NotImplementedError: TODO 1` | Every tool call checks the budget, so the designs cannot run until step 2 is done. |
| `test_workflow.py` cost is off by a few cents | A call's thread is wrong: the implement call must include every context file, and the describe call uses a new thread. |
| Golden `compare` differs only in the workflow and routed rows | Your `run_workflow` calls tools in a different order, or misses the `review` branch the routed design uses. |
| `test_only_chapter_10_files_are_added_or_changed` fails | A file changed in `relay-repo` that Chapter 10 does not own, or you left a scratch file there. |
| Reports are slow | The first report runs 1,440 simulated runs (about 5 seconds); later reports reuse them. |
| Golden tests fail after you edited `data/` | Regenerate with `python scripts/generate_data.py`; inputs written by hand are not regenerated. |

## Cleanup

Nothing to clean up. Every run uses an in-memory SQLite database and writes nothing outside `evidence/`.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Budgets and stop rules | 2 | `tests/test_budget_and_stop.py` and Relay's suite pass, and step 2's questions are answered |
| Workflow | 2 | `tests/test_workflow.py` passes and step 3 names what each agent decides that the workflow's code decides |
| Comparison | 2 | `tests/test_compare.py` and the golden tests pass; dev and held-out are used for different decisions |
| Design record | 3 | Every step classified with evidence; intervals, McNemar and power read correctly; a reviewer who is not the author |
| Tools review | 1 | Every tool's effect, scope and approval listed; the kill-switch question answered from the code |

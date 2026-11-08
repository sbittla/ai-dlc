# Lab 1.1 — Value-Stream Map and Baseline Metrics

| | |
| --- | --- |
| Chapter | 1 — From SDLC to Evidence-Driven Engineering |
| Type | Core (Builder, Platform, Security, Leader) |
| Time | 3 hours |
| Cost ceiling | $0 (runs locally, no cloud, no model calls) |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages. |

## Brief

Relay is built by a team of eight engineers. Its engineering manager wants to "roll coding agents out to everyone". Before anyone changes anything, you will establish **what delivery looks like today**, so any later claim of improvement can be checked against evidence.

You have two quarters of Relay's delivery history in `data/`:

- `2026Q1`: before the team adopted coding agents. This is your **baseline**.
- `2026Q2`: after about 85% of feature changes became AI-assisted.

You will implement the metric definitions, produce a baseline report, draw the current-state value-stream map, test one process change with a what-if, and write a measurement plan the team can keep using.

## What you will practise

- Turning vague goals ("faster", "better") into **precise, written metric definitions**.
- Computing DORA-style delivery metrics, flow metrics, queue metrics and a cost metric from raw events.
- Reading a value stream to find **where time is spent**: work or waiting.
- Spotting a metric that improves while the system gets worse, and a guardrail that raises false alarms.

## Folder layout

```
L1.1-value-stream-baseline/
├── README.md              ← you are here
├── pyproject.toml         ← Python version, pinned pytest, pytest settings
├── data/                  ← changes.csv, deployments.csv, costs.csv (generated, committed)
├── scripts/
│   └── generate_data.py   ← how the data was made (read it after the lab, not before)
├── starter/vsm/           ← YOUR WORK: implement the TODOs in metrics.py
│   ├── data.py            ← provided: loading and period slicing
│   ├── metrics.py         ← TODO: 10 functions
│   └── report.py          ← provided: prints the Markdown report
├── solution/vsm/          ← reference solution (instructors; do not peek until done)
├── templates/             ← value-stream map and measurement plan templates
├── tests/                 ← specification tests
└── evidence/              ← YOUR DELIVERABLES go here
```

## How the tests choose what to grade

Tests run against `starter/` by default. Instructors and CI set `LAB_TARGET=solution` to check the reference.

```bash
python -m pytest -q                          # grades your starter/ (bash, zsh or PowerShell)
LAB_TARGET=solution python -m pytest -q      # reference solution, bash or zsh
```

PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists in the session until removed, so always remove it, or later runs will silently grade the solution.

Run pytest from **this lab's folder**. Each lab has its own `conftest.py`, so running pytest across several labs at once from the repository root is not supported.

## Steps

### 1. Read the data (15 min)

Open the three CSV files. For each column in `changes.csv`, write one sentence in your notes on what event it records. Note that a change is assigned to the quarter in which it **deployed**, and that times are calendar hours (nights and weekends included).

### 2. Implement the metrics (75 min)

Open `starter/vsm/metrics.py`. Each TODO function has a docstring with the exact definition. Implement them one at a time and run the tests as you go:

```bash
python -m pytest -q -k change_fail_rate     # one metric at a time
python -m pytest -q                         # everything
```

The **fixture tests** (top of `tests/test_metrics.py`) are the specification: each uses a tiny dataset you can check on paper. The **golden tests** at the bottom compare your numbers with the reference values quoted in Chapter 1. If a fixture test passes but a golden test fails, you have made a definition choice that differs from the docstring; find it.

You may use a coding agent for this step. If you do, record in your measurement plan which functions it wrote, and check its work against the fixtures before accepting it. That is the habit this book is about.

### 3. Produce the baseline report (10 min)

```bash
cd starter
python -m vsm.report --data ../data --period 2026Q1 --compare 2026Q2 --monthly > ../evidence/baseline-report.md
```

On Windows PowerShell 5.1, `>` writes UTF-16. Use `... | Out-File -Encoding utf8 ../evidence/baseline-report.md` instead. PowerShell 7 writes UTF-8 by default.

### 4. Draw the current-state value-stream map (25 min)

Copy `templates/value-stream-map.md` to `evidence/value-stream-map.md`. Fill in the median hours for each stage from your **2026Q1** report, mark which stages are work and which are waiting, and record flow efficiency. Then complete the second map for 2026Q2.

### 5. Test one process change (15 min)

The report's last row is a what-if: feature-change lead time if Relay deployed every weekday at 15:00 instead of only on Tuesdays and Thursdays. Your `daily_deploy_counterfactual` computes it. In the "Target state" section of your map, compare its gain with the coding-time gain agents produced, and state the assumptions the what-if makes.

### 6. Write the measurement plan (40 min)

Copy `templates/measurement-plan.md` to `evidence/measurement-plan.md` and complete every section. The plan must include:

- each metric's definition, data source, owner and review cadence;
- at least two **guardrail metrics**, each with a threshold **and an evaluation window**. Use the monthly and rolling tables from `--monthly` to show that your window would not have raised a false alarm in Q1, before agents arrived;
- the one metric from your report that would mislead leadership if shown alone, and why.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/baseline-report.md` | The generated report for 2026Q1 vs 2026Q2, with the monthly table |
| `evidence/value-stream-map.md` | Both maps, work vs wait marked, flow efficiency, largest queue named, daily-deploy what-if |
| `evidence/measurement-plan.md` | All template sections complete, including guardrails with windows and the misleading metric |
| Passing tests | `python -m pytest -q` shows all tests passing against `starter/` |

## Sample of acceptable evidence (excerpt)

> **Where the time went.** In 2026Q2 the median change waited 16.9 hours for its first review, up from 5.4 hours. Coding time fell from 22.0 to 7.9 hours, so agents moved time into the review queue rather than removing it. Median lead time for feature changes rose from 80.8 to 89.8 hours.
>
> **Process what-if.** Deploying every weekday would cut median feature lead time in Q1 from 80.8 to 55.0 hours, about 26 hours, without any AI. It assumes the same merge times and no change in failure rates.
>
> **Misleading metric.** Cost per accepted change fell from $3,981 to $2,172. Shown alone, this suggests a 45% efficiency gain. In the same period change fail rate rose from 12.5% to 18.5% and rework rate from 8.3% to 22.2%. A "change" is not a unit of value.
>
> **Guardrail window.** A monthly 15% change-fail-rate guardrail would have fired in February (20%, 2 of 10 deployments), before agents arrived. A rolling three-month window stays at 12.5% for January–March and first fires on February–April (20%, 5 of 25), so I use rolling three-month windows with at least 20 deployments.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `ModuleNotFoundError: vsm` | Run `pytest` from the lab folder, and `python -m vsm.report` from inside `starter/`. |
| Lead time off by tens of hours | You started the clock at `pr_opened_at` or `merged_at` instead of `first_commit_at`. |
| Flow efficiency too high | You averaged per-change ratios, or included hotfixes. Sum hours across feature changes. |
| p90 differs slightly | Use the provided nearest-rank `percentile`, not `statistics.quantiles` (it interpolates). |
| Deployments per week is 2.00 | You used 12 weeks. Periods are calendar quarters: 2026Q1 is 90 days, about 12.86 weeks. |
| Tests pass but should not | `LAB_TARGET` is still set to `solution` in your shell. Remove it. |

## Cleanup

Nothing to clean up. No cloud resources or credentials are used.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Metrics correct | 3 | All tests pass against `starter/` |
| Value-stream maps and what-if | 2 | Both periods, work and wait distinguished, largest queue named with numbers, what-if with assumptions |
| Measurement plan | 3 | Definitions, owners and cadence for every metric; two guardrails with thresholds and windows; data-quality risks named |
| Interpretation | 2 | Explains, with numbers, why faster coding did not mean faster delivery, and names the misleading metric |

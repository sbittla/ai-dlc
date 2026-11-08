# Lab 7.1 — Triage Eval Suite and CI Gate

| | |
| --- | --- |
| Chapter | 7 — Evaluation-Driven Development |
| Type | Core (Builder, Platform, Security) |
| Time | 4 hours |
| Cost ceiling | $0 offline (default). Live mode: about $2–4 for two candidates × 200 tickets × 3 runs on `claude-opus-5-5` at the list prices in `models.py` (thinking tokens vary). The gate refuses to start a live run without `--max-usd`, stops calling at that ceiling, and fails closed on an incomplete run. Check current prices first |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). Live mode only: `pip install -e ".[live]"` and Claude API credentials |

## Brief

In Chapter 7's opening incident, a one-paragraph change to Relay's triage prompt fixed five demo tickets and quietly broke production. Nobody ran an evaluation, because there was no evaluation that a pull request could run.

You will build one. It has four parts:

1. A **versioned, labelled dataset**: 300 tickets, 100 for development and 200 held out, with adversarial and fairness slices, pinned by version and hash.
2. A **gate** that compares a candidate (a model plus a prompt version) with the production baseline on the same held-out tickets, with paired statistics and a written threshold policy. It exits with status 1 when the candidate regresses beyond noise, so CI can block the merge.
3. **Leakage checks** that keep held-out tickets out of everything that gets tuned.
4. The **difficulty router** that Chapter 2 left open, trained on dev tickets and judged on held-out ones.

## Simulated and live models

By default the suite runs **simulated** models: `sim-large`, `sim-large-2` and `sim-small`. They are seeded random processes, not real models. Their behaviour is *configured* in `models.py`: how often each is right on each kind of ticket under each prompt version, how often it breaks the schema, and how often it obeys an injected instruction.

Every pattern you will find was put there to be found: the triage-v2 regression, the German slice of `sim-large-2`, the small model's weakness on hard tickets. The skill this lab teaches is building and reading the gate, not learning facts about models. Never quote simulated numbers as facts about real models. The simulator is configured separately from Lab 2.1's, so its numbers on the 40 Chapter 2 tickets differ from Table 2.6.

Two results are *not* configured. The router (`router.py`) is real code trained on real text, so its held-out recall, and how much a row split inflates it, are measurements. So are the dataset's leakage counts.

Live mode runs the same gate against real Claude models through the official Anthropic SDK, with structured outputs. The adapter is copied from Lab 2.1. Refusals, truncation, API errors and budget stops are recorded as outcomes, never raised.

## What you will practise

- Designing a dataset that measures what you care about: **slices**, **families** and a **held-out split** nobody tunes on.
- **Paired comparisons**: McNemar counts, a paired bootstrap interval and a sample-size calculation.
- Writing a **threshold policy** that fails real regressions, does not fail noise, and says when the evidence is too thin.
- Catching **evaluation leakage** before it inflates a score.
- Evaluating a **router** on held-out data before routing any traffic.

## Folder layout

```
L7.1-triage-eval-gate/
├── data/
│   ├── tickets.jsonl            ← 300 labelled tickets (generated; do not edit)
│   ├── manifest.json            ← name, version 2026.11.1, content hash, counts by split and slice
│   ├── gate-policy.json         ← the threshold policy, triage-gate-v1
│   ├── agent-tasks.jsonl        ← 30 coding tasks for the instruction-file evaluation
│   └── source/ch02-tickets.jsonl  ← Lab 2.1's 40 tickets, copied unchanged
├── scripts/
│   ├── generate_data.py         ← writes tickets, manifest and agent tasks (deterministic)
│   └── update_golden.py         ← instructors: regenerate tests/golden/ after a deliberate change
├── starter/evalsuite/
│   ├── schema.py, prompts.py    ← provided: triage schema; prompt versions v1, v1.1, v2, v3, v3.1
│   ├── models.py                ← provided: simulated models, live adapter, budget guard
│   ├── runner.py                ← provided: runs a candidate, strict parsing, summaries
│   ├── dataset.py               ← TODO: check_leakage
│   ├── stats.py                 ← TODO: mcnemar_exact, paired_bootstrap, paired_sample_size
│   ├── gate.py                  ← TODO: evaluate_gate
│   ├── router.py                ← TODO: choose_threshold
│   ├── agent_eval.py            ← provided: the simulated instruction-file evaluation
│   └── report.py                ← provided: the gate CLI and every report the chapter quotes
├── solution/evalsuite/          ← reference solution
├── templates/
│   ├── eval-gate-record.md      ← the record you file with a gated change
│   └── eval-gate.yml            ← an illustrative CI workflow for Relay's repository
├── tests/                       ← specification tests and golden reports
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Run pytest from this lab's folder.

Tests of provided code (`test_models.py`, most of `test_dataset.py`) pass before you start. Every other failure is a `NotImplementedError` from one of the six TODOs.

## Steps

### 1. Read the dataset, the manifest and the policy (20 min)

Read `data/manifest.json` and `data/gate-policy.json`, then twenty tickets of different kinds. Run:

```bash
cd starter
python -m evalsuite.report --data ../data dataset
```

Answer in your record: why does a family never cross the split? Why are the 40 Chapter 2 tickets in dev, not held out? Which slices are too small to read on their own?

### 2. Paired statistics (45 min)

Implement `mcnemar_exact`, `paired_bootstrap` and `paired_sample_size` in `starter/evalsuite/stats.py`. Each docstring gives the exact procedure; the bootstrap must follow it step by step, because the golden tests depend on its random draws.

```bash
python -m pytest -q tests/test_stats.py
```

### 3. Leakage checks (30 min)

Implement `check_leakage` in `dataset.py`: family overlap, held-out text inside the prompt, and near-duplicates across the split.

```bash
python -m pytest -q tests/test_dataset.py
```

### 4. The gate (55 min)

Implement `evaluate_gate` in `gate.py`. The docstring lists nine rules in order. Every rule is evaluated even after a failure, so a report shows everything that is wrong. Warnings never fail the gate.

```bash
python -m pytest -q tests/test_gate.py
cd starter
python -m evalsuite.report --data ../data gate --candidate sim-large:triage-v2
echo $?          # 1: the gate failed (PowerShell: $LASTEXITCODE)
```

### 5. The router's threshold (20 min)

Implement `choose_threshold` in `router.py`. Then run the router report and compare its recall on dev (its own training data) with its recall on held-out tickets.

### 6. Run every report and read it like a reviewer (25 min)

```bash
cd starter
python -m evalsuite.report --data ../data candidates > ../evidence/candidates.md
python -m evalsuite.report --data ../data incident
python -m evalsuite.report --data ../data leakage
python -m evalsuite.report --data ../data router
python -m evalsuite.report --data ../data stats
python -m evalsuite.report --data ../data agents
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

For each candidate in `candidates.md`, say in one sentence why it passed or failed. Then answer: why does triage-v3 fail although its score is higher than triage-v3.1's? Why does `sim-large-2` fail although it improves overall? Why do the McNemar p-value and the bootstrap interval disagree for triage-v3.1?

### 7. Live run (optional, 15 min, costs money)

Only with an approved budget and credentials:

```bash
pip install -e ".[live]"
cd starter
python -m evalsuite.report --data ../data gate --live --max-usd 5 \
    --baseline claude-opus-5-5:triage-v1 --candidate claude-opus-5-5:triage-v2 > ../evidence/gate-live.md
```

Record the date, model IDs and spend. Do not mix live and simulated numbers in one decision.

### 8. File the gate record (30 min)

Copy `templates/eval-gate-record.md` to `evidence/` and complete it for one candidate: triage-v3.1, or `sim-large-2` as a model upgrade. Then read `templates/eval-gate.yml` and write down what you would change before using it in your own repository.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/candidates.md` | The generated candidates table |
| `evidence/eval-gate-record.md` | Every template section, with the gate's rule table, intervals and slice sizes |
| `evidence/gate-live.md` | Optional: a live gate report, with the date, model IDs and spend |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> Candidate `sim-large:triage-v3.1` (simulated) against the production baseline `sim-large:triage-v1`, on the 200 held-out tickets of relay-triage-eval 2026.11.1, 3 runs each. Gate PASS with one warning. Fully correct rose from 82.2% to 86.0%; the paired difference is +3.8 points (95% interval +1.7 to +6.2), so this is an improvement, not noise. Exact McNemar on majority-of-runs counts (1 worse, 7 better) gives p = 0.070; it uses less information than the interval, and the decision rule is the interval. The cost warning is real: examples raise cost per correct answer by 87%, from $0.001341 to $0.002510. Slices of 20 German and 20 Spanish tickets are too small to read alone. Decision: merge, and measure prompt caching on the longer prompt.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Golden report differs only in interval bounds | `paired_bootstrap` draws differently. Use `rng.choice(diffs)` `len(diffs)` times per resample, and the exact indices in the docstring. |
| `test_bootstrap_follows_the_docstring_exactly` fails | Same cause; or you used `random.choices` or `random.sample`, which consume the generator differently. |
| triage-v1.1 fails the regression rule | Your rule fails on any negative point estimate. A regression must be beyond noise (`high < 0`), or a larger drop than the margin must be possible (`low < -margin`). |
| A slice rule fails where the reference warns | The slice fails only when its interval is entirely below zero. |
| `dataset` rule fails after editing a ticket | Working as intended. A changed dataset is a new version: regenerate, bump `VERSION`, and update the policy's pin. |
| `ModuleNotFoundError: anthropic` | Live mode only. `pip install -e ".[live]"`. |
| A live gate fails on `complete` | The spend ceiling stopped some calls. Raise `--max-usd` within your budget, or reduce the candidates. The gate never passes on an incomplete run. |

## Cleanup

Offline: nothing. Live: no resources are created; check your provider's usage page for the spend.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Statistics and gate correct | 3 | All tests pass against `starter/` |
| Reading the gate | 2 | Every candidate's result explained from its rules; noise not called a difference; small slices called small |
| Leakage and the router | 2 | Explains why v3 fails, what the row split does to the router's recall, and why the router is not yet routing traffic |
| Gate record | 2 | Complete, with pinned dataset version, intervals, warnings acknowledged and a rollout step |
| CI workflow | 1 | A reasoned list of changes to `eval-gate.yml` for a real repository (paths, credentials, budget, required check) |

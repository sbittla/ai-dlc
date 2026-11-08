# Lab 7.2 — Calibrate an LLM Judge Against Human Labels

| | |
| --- | --- |
| Chapter | 7 — Evaluation-Driven Development |
| Type | Stretch (Builder, Platform) |
| Time | 3 hours, including the optional 15-minute live run |
| Cost ceiling | $0 offline (default). Live mode: under $1 for one judge prompt over the 120 held-out answers and 60 pairs (240 calls) on `claude-opus-5-5` at the list prices in `judges.py`; the judge stops calling at `--max-usd` and records every unanswered item. Check current prices first |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`, pinned to `pytest==9.1.1`). Live mode only: `pip install -e ".[live]"` (the Anthropic SDK, a pinned range `>=2.6,<3`, as in Lab 2.1) and Claude API credentials |

## Brief

Triage can be scored by exact match. The answers of Relay's support assistant cannot: whether "Relay retries 8 times over about 6 hours" is right needs a reading. Relay's support leads can label a few hundred answers a release. A language model used as a judge can label thousands, but only if it agrees with the leads closely enough, and does not prefer what is long, what it wrote itself, or what it saw first.

You will measure that agreement on 180 human-labelled answers and 90 answer pairs, probe the judge for three known biases, and apply a written rule that decides whether the judge may replace human labels, and for which use.

## Simulated and live judges

By default the lab runs two **simulated** judges, `judge-v1` (asks "is this a good answer?") and `judge-v2` (checks the answer against a reference, and is told that length does not count). They are seeded random processes, not models. Their biases are *configured* in `judges.py`: how often each passes a wrong answer when it is long or written by its own model family, and how often it picks whichever answer it is shown first.

The probes will find exactly these biases, because they were put there. What this lab teaches is the calibration method, and how small the evidence for each bias is. Never quote simulated numbers as facts about real judges. The answers and labels are synthetic too: each question asks about one canonical Relay fact, and the adjudicated label stands in for the support leads' judgement.

Live mode runs the same calibration with a real Claude model as the judge. Refusals, truncation, invalid output, API errors and budget stops become "no verdict", which counts as disagreement with the humans.

**The self-preference probe has two limits.** In live mode it is meaningless as shipped: the answers labelled "large" were written by the generator, not by the judge's model, so a real judge has no reason to recognise them. To probe self-preference live, replace them with answers your judge's own model wrote. Even then, the probe is confounded if the two families make different kinds of mistakes, because some wrong answers are simply easier to catch than others. Compare families on matched questions, as this dataset does, and treat the gap as a lead to investigate, not a verdict.

## What you will practise

- Measuring agreement with **Cohen's kappa** and a **confusion matrix**, not raw accuracy.
- Comparing the judge with how well **people agree with each other**.
- **Bias probes**: verbosity, self-preference and position, and how few items each probe rests on.
- A **decision rule**, chosen on a calibration split and applied to a held-out split.

## Folder layout

```
L7.2-judge-calibration/
├── data/
│   ├── answers.jsonl         ← 180 answers: question, reference, answer, style, source family, two labellers, adjudicated label
│   ├── pairs.jsonl           ← 90 pairs (one right, one wrong answer) with the human preference
│   ├── judge-policy.json     ← the decision rule, judge-policy-v1
│   └── manifest.json         ← version and content hashes
├── scripts/generate_data.py  ← writes everything in data/ (deterministic)
├── starter/judgecal/
│   ├── judges.py             ← provided: simulated judges, judge prompts, the live judge
│   ├── metrics.py            ← TODO: confusion, cohen_kappa, swap_consistency
│   ├── calibrate.py          ← provided: runs a judge and computes every measure
│   ├── policy.py             ← TODO: check_results
│   └── report.py             ← provided: agreement, probes and decide reports
├── solution/judgecal/        ← reference solution
├── templates/judge-calibration-record.md
├── tests/
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Run pytest from this lab's folder.

## Steps

### 1. Read the data, the rubric and the policy (15 min)

Read ten answers and five pairs, `data/manifest.json`'s rubric, and `data/judge-policy.json`. Write down which error matters more for a regression gate, a false pass or a false fail, and why.

### 2. Agreement: confusion matrix and kappa (40 min)

Implement `confusion` and `cohen_kappa` in `starter/judgecal/metrics.py`.

```bash
python -m pytest -q tests/test_metrics.py -k "confusion or kappa"
```

`test_kappa_is_not_accuracy` shows why kappa exists: two raters who agree 90% of the time can have a kappa of 0.

### 3. Position: swap consistency (15 min)

Implement `swap_consistency`. A judge that picks the same *answer* in both orders gives different *letters*.

### 4. The decision rule (25 min)

Implement `check_results` in `policy.py`. Every limit is inclusive.

```bash
python -m pytest -q
```

### 5. Choose a judge prompt on the calibration split (20 min)

```bash
cd starter
python -m judgecal.report --data ../data agreement > ../evidence/agreement.md
python -m judgecal.report --data ../data probes --split calibration
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

Choose between `judge-v1` and `judge-v2` from the calibration rows only. Note which calibration differences rest on ten items or fewer.

### 6. Probe and decide on the held-out split (30 min)

Still in `starter/`:

```bash
python -m judgecal.report --data ../data probes > ../evidence/probes.md
python -m judgecal.report --data ../data decide > ../evidence/decide.md
cd ..
```

Answer: why does `judge-v2` agree with the adjudicated labels slightly more than two labellers agree with each other, and why does that not make it better than a person? Which check does `judge-v2` pass with no margin at all, and on how many answers? Why may it grade single answers but not compare pairs?

### 7. Live judge (optional, 15 min, costs money)

```bash
pip install -e ".[live]"          # from the lab folder, where pyproject.toml is
cd starter
python -m judgecal.report --data ../data decide --live judge-v2 --model claude-opus-5-5 --max-usd 1 > ../evidence/decide-live.md
cd ..
```

Record the date, model ID, spend and every "outcome other than a verdict".

### 8. Write the calibration record (20 min)

Copy `templates/judge-calibration-record.md` to `evidence/` and complete it.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/agreement.md`, `evidence/probes.md`, `evidence/decide.md` | The generated reports |
| `evidence/judge-calibration-record.md` | Every template section, with kappa intervals and the n behind each probe |
| `evidence/decide-live.md` | Optional: a live calibration, with the date, model ID and spend |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> On the 120 held-out answers, the simulated `judge-v2` agreed with the adjudicated labels at kappa 0.87 (95% 0.77 to 0.95) and passed 3 of 60 wrong answers (5.0%). Two labellers agree with each other at kappa 0.82. Its self-preference gap is exactly the policy's limit of 10 points: 3 of 30 false passes on its own family's wrong answers against 0 of 30 on the other family's. That is three answers, too few to show the judge is unbiased, so the 10% human audit sample must track it. In pairs it chose the same answer in both orders only 76.7% of the time. Decision: `judge-v2` may grade single answers against a reference; pairwise comparisons stay with humans.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Kappa is right on the fixtures but wrong with `None` verdicts | `None` is a label of its own in p_e, and never agreement. |
| Confusion counts are off by the number of `None` verdicts | A `None` on a human 'fail' counts as fp, not tn. |
| Swap consistency is 1 minus the reference | Same letters in both orders mean *different* answers. |
| A check fails exactly at its limit | Limits are inclusive: `>=` and `<=`. |
| `ModuleNotFoundError: anthropic` | Live mode only. `pip install -e ".[live]"`. |

## Cleanup

Offline: nothing. Live: no resources are created; check your provider's usage page for the spend.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Metrics and rule correct | 3 | All tests pass against `starter/` |
| Choosing on calibration | 2 | The prompt is chosen from calibration rows only, with the small-sample cautions stated |
| Reading the probes | 3 | Each bias quoted with its n; the edge-case self-preference result explained; pairwise refusal explained |
| Decision and controls | 2 | Clear scope for the judge, the audit sample, and the recalibration triggers |

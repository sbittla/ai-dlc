# Lab 4.2 — An Eval That Finds Seeded Requirement Ambiguities

| | |
| --- | --- |
| Chapter | 4 — Discovery and Requirements with AI |
| Type | Stretch (Builder, Platform) |
| Time | 2 hours |
| Cost ceiling | $0 offline (default). Live mode: the `--max-usd` ceiling, $1.00 by default; one held-out run of 48 statements is estimated at under $0.25 with `claude-opus-5-5` and under $0.01 with `claude-haiku-5-5` at the list prices in `models.py`. Check current prices and set a spend limit first |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). Live mode only: `pip install -e ".[live]"`, which installs the Anthropic SDK within a pinned version range (`anthropic>=2.6,<3`, as in Lab 2.1), and Claude API credentials |

## Brief

Lab 4.1's checker finds vague words it has been told about. Relay's product owner wants to know how good such a check really is before making it a required status check on every PRD change, and whether a language model would do better.

You will build the evaluation that answers her. It uses 96 requirement statements with **seeded defects**, labelled by type: **ambiguity**, **untestable**, **contradiction** and **missing actor**. A rule-based detector is the baseline. Your harness scores **precision and recall per defect type**, each with a Wilson interval, exactly as defined in Chapter 2.

The data has a **dev split** for tuning and a **held-out split** for reporting. One lexicon, v2, was tuned by reading the detector's misses on dev. Your job is to report what that tuning bought where it counts.

## The data, honestly described

The statements are synthetic. The authors wrote them and seeded the defects, and a second reader reviewed the labels once. The held-out sets were written later, by a different author who had not seen the dev sets or the detector, so they use some different words. That gap between the splits was built into the data, as the gap between keyword and paraphrased questions was in Lab 2.2. What transfers is the discipline of tuning on one split and reporting on another, not the particular percentages.

Two of the detector's rules are flattered by the data's shape. The contradiction rule compares only statements within the same labelled set of four, and a real PRD has no such sets: run on a whole PRD, it would compare every pair and raise more false alarms. The missing-actor rule was written by the same authors who wrote the statements. Both rules are candidates for Relay's gate, not part of it. Lab 4.1's RQ030 is a different rule: it compares declared `Value:` keys, so its answer is exact.

Labelling rules (a statement may have none, one or several):

| Defect | Labelled when |
| --- | --- |
| ambiguity | A word or phrase two careful readers could interpret differently ("the relevant people", "quickly") |
| untestable | No observation could show it false: a weak modal ("should", "is expected to"), or a quality of the system's behaviour with no threshold ("highly available"). A vague *quality* ("quickly") is both ambiguity and untestable; a vague *noun phrase* ("the relevant people") is ambiguity only |
| contradiction | It cannot be true at the same time as another statement in its set; both statements are labelled, and each names the other |
| missing_actor | It does not name who performs the action or who receives its result ("A summary email is sent at the end of each hour") |

## What you will practise

- Turning a quality check into an **evaluation**: labelled data, a scoring rule written in advance, intervals.
- **Precision and recall per type**, and why a pooled number hides the type a check cannot see.
- **Held-out discipline**: tune on dev, report on held-out (Chapter 2's evaluation leakage).
- Running a model under a **cost ceiling**, with refusals, truncation and API errors recorded as outcomes.

## Folder layout

```
L4.2-ambiguity-eval/
├── data/
│   ├── statements.jsonl        ← 96 labelled statements: id, set, split, topic, text, defects, conflicts_with
│   ├── lexicon-v1.json         ← baseline detector lexicon (from Lab 4.1, plus quality words and actor terms)
│   └── lexicon-v2.json         ← v1 plus 4 vague words and 1 quality word found by reading dev misses
├── scripts/generate_data.py    ← writes data/ (deterministic; byte-identical on every platform)
├── starter/ambeval/
│   ├── data.py                 ← provided: loaders
│   ├── detector.py             ← TODO: detect_missing_actor; the other rules are provided
│   ├── scoring.py              ← TODO: confusion, rates; wilson_interval is provided (Lab 2.1's)
│   ├── prompt.py               ← provided: the versioned live prompt and output schema
│   ├── models.py               ← provided: the live Claude adapter (Lab 2.1's pattern)
│   ├── live.py                 ← provided: runs a model under a cost ceiling; every failure is an outcome
│   └── report.py               ← provided: the tables, --errors, --live
├── solution/ambeval/           ← reference solution
├── templates/eval-record.md
├── tests/
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists until removed, so always remove it. Run pytest from this lab's folder. Until you finish, every failing test stops with `NotImplementedError`.

## Steps

### 1. Read the definitions and the detector (10 min)

Read the labelling rules above, `starter/ambeval/detector.py` and both lexicons. Predict which defect type the rules will find worst, and why.

### 2. Label a sample yourself, blind (15 min)

Without looking at the `defects` field, label statements S001–S012 (sets D01–D03) with the rules above. Then compare. Count your agreements. Where you disagree, decide whether the label or you misread the rule. Human disagreement sets a ceiling on how good any detector can look.

### 3. Implement the TODOs (30 min)

| Function | What it decides |
| --- | --- |
| `scoring.confusion` | For one defect type, how many statements were true positives, false positives, false negatives and true negatives? |
| `scoring.rates` | Precision and recall, each with a Wilson interval; undefined rates are `None`, not 0% |
| `detector.detect_missing_actor` | A passive verb and no named actor |

```bash
python -m pytest -q tests/test_scoring.py
python -m pytest -q
```

### 4. Run the baseline on dev and read its errors (15 min)

```bash
cd starter
python -m ambeval.report --data ../data/statements.jsonl --lexicon ../data/lexicon-v1.json --split dev --errors dev
```

For each miss, name the word or construction the rule could not see. Would adding a word fix it, or does the defect need understanding the rule does not have?

### 5. Compare v1 and v2, then look at held-out (15 min)

```bash
cd starter
python -m ambeval.report --data ../data/statements.jsonl --lexicon ../data/lexicon-v1.json --lexicon ../data/lexicon-v2.json > ../evidence/eval-offline.md
python -m ambeval.report --data ../data/statements.jsonl --lexicon ../data/lexicon-v2.json --errors heldout
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

What did v2 buy on dev? On held-out? Which lexicon would you ship, and why? Which type would you never let this detector be the only check for?

### 6. Live run (optional, 15 min, costs money)

Only with an approved budget and credentials. Run on held-out only:

```bash
cd starter
python -m ambeval.report --data ../data/statements.jsonl --lexicon ../data/lexicon-v1.json --split heldout --live claude-haiku-5-5 --max-usd 0.50 > ../evidence/eval-live.md
```

The report prints the spend and every outcome by kind. A failed statement counts as "no defects flagged", so failures lower recall instead of disappearing. The ceiling stops new calls once spend reaches it; the last call can take spend past it by at most one call's cost. Do not tune the prompt on held-out: if you change the prompt, run it on dev first, and say in your record that held-out was used once.

### 7. Write the evaluation record (20 min)

Copy `templates/eval-record.md` to `evidence/` and complete it.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/eval-offline.md` | The generated v1 and v2 report |
| `evidence/eval-record.md` | Every template section, with numbers and intervals from your reports |
| `evidence/eval-live.md` | Optional: the live report, with the date and model ID |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> On held-out, the v1 detector flagged 22 defects, 21 correctly: precision 95% (78%–99%), recall 60% (44%–74%), pooled over 35 labelled defects. Recall differs by type: missing actor 8 of 8, contradiction 4 of 8, untestable 6 of 12, ambiguity 3 of 7. Each type has only 7 to 12 positives, so each recall interval is between 32 and 59 points wide. Tuning on dev (v2) raised dev recall from 75% to 88% and changed nothing on held-out, where the new words never occur. Lab 4.1's word-list checks (RQ010–RQ012) therefore stay warnings: on 3 and 6 held-out flags, the precision intervals reach down to 44% and 61%, too little evidence to block a merge. We keep v1's words and record v2's as hypotheses for a larger held-out set. The contradiction and missing-actor rules stay candidates, outside the gate. The contradiction rule misses every conflict that is not a difference in numbers, and only compares statements within a set, so a person still reads every pair of requirements that share a topic.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Precision is 0% for a type nobody flagged | Undefined is not zero: return `None` when tp + fp = 0. |
| Wilson test fails | Use the provided `wilson_interval`; do not reimplement p ± 1.96·SE. |
| "relay" or "owner" counted as an actor | Actor terms are matched case-sensitively: the product is "Relay", the role is "Owner". |
| Missing-actor recall lower than the reference | Check the "by <word>" rule, and that you test the passive pattern before the actor terms. |
| `ModuleNotFoundError: anthropic` | Live mode only: `pip install -e ".[live]"`. |
| Live run shows `refusal` or `api_error` | Recorded as outcomes. Report them; do not retry silently. |

## Cleanup

Offline: nothing. Live: no resources are created; check your usage page for the spend.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Scoring correct | 3 | All tests pass against `starter/` |
| Held-out discipline | 2 | Recommendation follows held-out, not dev; tuning gains reported on both splits |
| Statistical reading | 2 | Intervals used; small per-type counts called small; no claim inside the noise |
| Error analysis | 2 | Misses explained by mechanism; names the type the detector cannot be trusted with |
| Decision | 1 | Where the check runs, what it blocks or warns, and what a person still reviews |

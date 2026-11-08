# Evaluation Record — Requirement-Defect Detector

Copy to `evidence/eval-record.md` and complete it with numbers from your reports.

| Field | Value |
| --- | --- |
| Dataset | `data/statements.jsonl`, 96 statements (48 dev, 48 held-out) |
| Detectors compared | e.g. `detector-lexicon-v1`, `detector-lexicon-v2`, a live model |
| Live model ID, prompt version, date, spend | (if you ran live mode) |
| Who labelled the data, and how disagreements were settled | |

## 1. Your labels against the dataset's

For the 12 dev statements you labelled blind (step 2): how many of your labels matched? Which defect type did you disagree on most, and why? What does that disagreement imply about the best score any detector can show?

## 2. Results on held-out

| Defect | Positives | Precision (95% CI) | Recall (95% CI) |
| --- | ---: | ---: | ---: |
| ambiguity | | | |
| untestable | | | |
| contradiction | | | |
| missing_actor | | | |

Which differences between detectors are larger than the intervals? Say so plainly when a difference is one or two statements.

## 3. What tuning on dev did

Dev and held-out results for v1 and v2. What did the four added words buy on each split? Which lexicon do you recommend, and why?

## 4. Error analysis

Three held-out misses and the one false alarm, each with the reason the rule failed.

## 5. Live mode (optional)

Outcomes by kind (ok, refusal, truncated, api_error, invalid_json, schema, budget_exhausted), and the spend against the ceiling. Do not mix live and offline numbers in one comparison without saying so.

## 6. Decision

Where this detector runs (for example, as a required check on every PRD change), what it may block, what it may only warn about, and what a person still reviews. What result would change your decision?

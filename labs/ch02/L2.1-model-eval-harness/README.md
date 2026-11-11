# Lab 2.1 — A Model Evaluation Harness

| | |
| --- | --- |
| Chapter | 2 — LLMs for Engineers: Models, Context and Failure Modes |
| Type | Core (Builder, Platform, Security) |
| Time | 4 hours |
| Cost ceiling | $0 offline (default). Live mode: typical run about $0.40 for two models × 40 tickets × 3 repeats at the list prices in `models.py`; the `--max-usd` guard is the hard limit (default $2.00, split equally between the models). Both figures are modelled with a mock (`labs/verify-illustrations/mock-live-runs/`), not measured, until one real run; thinking tokens vary. Check current prices first |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). Live mode only: `pip install -e ".[live]"` and Claude API credentials |

## Brief

Relay wants AI to triage incoming support tickets: assign a **category**, a **priority** and the **team** that should handle it. Two models are on the shortlist, a large one and a small one. The small one is about 40 times cheaper per call. Your job is to build the harness that decides, with evidence, which model (if either) is good enough for which tickets.

You will evaluate on 40 real-looking Relay tickets with human-agreed labels (`data/tickets.jsonl`): 20 easy, 20 hard. One hard ticket contains a prompt-injection attempt.

## Simulated and live models

The simulator's behaviour is *configured*, in `models.py`: its accuracy by difficulty, how often it errs on each field, its injection rate. The patterns you find in the offline table were put there to be found. The skill this lab teaches is reading such a table, not learning facts about small models.

By default the harness runs two **simulated** models, `sim-large` and `sim-small`. They are seeded random processes, not real models. Their accuracy, formatting errors, latency and token use are set to plausible values so everyone gets identical, free results while learning to build and read an evaluation. Never quote simulated numbers as facts about real models.

Live mode runs the same harness against real Claude models through the official Anthropic SDK, with structured outputs. Results will differ from the simulation, and from run to run. That difference is part of the lesson.

## What you will practise

- Treating model output as **untrusted input**: parse strictly, validate against a schema, never "repair" silently.
- Scoring field by field, with **repeat runs** and **confidence intervals**, not one lucky run.
- Measuring **consistency**, **latency percentiles** and **cost per correct answer**, not only accuracy.
- Writing a **model selection decision record** that a skeptical colleague could check.

## Folder layout

```
L2.1-model-eval-harness/
├── data/tickets.jsonl          ← 40 labelled tickets (id, difficulty, text, expected)
├── starter/harness/
│   ├── schema.py               ← provided: triage schema and a small validator
│   ├── prompt.py               ← provided: the versioned triage prompt
│   ├── models.py               ← provided: simulated models, the live Claude adapter and its spend guard
│   ├── runner.py               ← provided: runs every model × ticket × repeat, summarises
│   ├── scoring.py              ← TODO: 5 functions
│   └── report.py               ← provided: prints the comparison table
├── solution/harness/           ← reference solution
├── templates/model-decision-record.md
├── tests/
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Run pytest from this lab's folder.

## Steps

### 1. Read the tickets and the prompt (20 min)

Read all 40 tickets and `prompt.py`. For five hard tickets, write down which label you would have chosen and why. Notice where reasonable people could disagree: that disagreement caps how accurate any model can look.

### 2. Implement scoring (90 min)

Implement the five TODO functions in `starter/harness/scoring.py`:

| Function | What it decides |
| --- | --- |
| `parse_output` | Is this text valid JSON that matches the schema? No stripping, no repair. |
| `score_prediction` | Which of the three fields are right? |
| `cost_usd` | What did one call cost, from token counts and prices? |
| `wilson_interval` | How uncertain is an accuracy measured on n calls? |
| `consistency_rate` | Did repeat runs on the same ticket agree? |

```bash
python -m pytest -q -k parse_output
python -m pytest -q
```

### 3. Run the offline evaluation (10 min)

```bash
cd starter
python -m harness.report --data ../data/tickets.jsonl --repeats 5 --tokens --by-ticket > ../evidence/eval-offline.md
```

`--tokens` adds the estimated token budget of one request. `--by-ticket` adds intervals that resample tickets instead of calls, because repeat runs of one ticket are not independent. On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

### 4. Read the results like a reviewer (40 min)

Answer in your decision record, with numbers from your report:

1. Is the accuracy difference between the models larger than the uncertainty? (Compare the intervals.)
2. Where does the small model lose accuracy: easy or hard tickets, and which field?
3. How often is each model's output unusable, and what kinds of failure occur?
4. What does the consistency figure tell you about running each ticket once in production?
5. What did each model do with ticket TK32, the injection attempt?
6. What does a correct answer cost from each model?

### 5. Live run (optional, 30 min, costs money)

Only with an approved budget and credentials:

```bash
cd starter
python -m harness.report --data ../data/tickets.jsonl --repeats 3 --live claude-opus-5-5,claude-haiku-5-5 > ../evidence/eval-live.md
```

The `--max-usd` guard (default $2.00) gives each model an equal share and checks every call before making it: if the call's worst-case cost (a pessimistic input estimate, and every output token up to `max_tokens` billed) would take that model's spend past its share, the call is not made and is recorded as a failure of kind `budget`. The report ends with the spend and the number of calls the budget stopped. A run with budget stops is incomplete: raise `--max-usd` within your budget, or run fewer repeats.

Compare the live and simulated tables. Note where they differ, and do not mix numbers from the two in your decision.

### 6. Write the decision record (40 min)

Copy `templates/model-decision-record.md` to `evidence/` and complete it. A good decision may use **both** models: for example, the small model for easy tickets with a confidence check, and the large model for hard or high-risk ones.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/eval-offline.md` | The generated offline report |
| `evidence/model-decision-record.md` | Every template section, with numbers and intervals |
| `evidence/eval-live.md` | Optional: the live report, with the date and model IDs |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> On the simulated evaluation, `sim-large` was fully correct on 88.5% of 200 calls (95% interval 83.3%–92.2%) and `sim-small` on 71.0% (64.4%–76.8%). The intervals do not overlap, so the difference is real for this ticket set. The gap is almost entirely on hard tickets: 81.0% vs 52.0%, against 96.0% vs 90.0% on easy ones. `sim-small` produced 11 unusable outputs in 200 (5.5%): 5 with prose before the JSON and 6 that broke the schema, and obeyed the injected instruction in TK32 in 3 of 5 runs. Per correct answer, `sim-small` costs $0.000039 against $0.001241. Decision: neither model alone; route by difficulty, and never let triage output trigger an action without validation.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Accuracy higher than the reference | `parse_output` is stripping prose or code fences. Do not repair output. |
| Wilson interval test fails at the edges | Clamp to [0, 1], and use the formula in the docstring, not p ± 1.96·SE. |
| Consistency test fails | An invalid run (`None`) counts as a distinct answer. |
| `ModuleNotFoundError: anthropic` | Live mode only. `pip install -e ".[live]"`. |
| Live run returns `refusal` | Recorded as a failure of kind `refusal`. Report it; do not retry silently. |
| Live run shows failures of kind `budget` | The `--max-usd` guard stopped calls whose worst case would pass the ceiling. Raise it within your budget, or reduce repeats. |

## Cleanup

Offline: nothing. Live: no resources are created; check your usage page for the spend.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Scoring correct | 3 | All tests pass against `starter/` |
| Statistical reading | 2 | Uses intervals and repeat runs; does not claim differences inside the noise |
| Failure analysis | 2 | Failure kinds, consistency and the injection result discussed with numbers |
| Decision record | 3 | Clear decision per ticket type, cost per correct answer, risks, and what would change the decision |

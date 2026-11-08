# Lab 2.2 — One Question Set, Five Context Strategies

| | |
| --- | --- |
| Chapter | 2 — LLMs for Engineers: Models, Context and Failure Modes |
| Type | Stretch (all technical tracks) |
| Time | 3 hours |
| Cost ceiling | $0 offline (default). Live mode: under $1 with a small model for 46 questions × 3 strategies; check current prices first |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). Live mode only: `pip install -e ".[live]"` and Claude API credentials |

## Brief

Relay's support assistant answers customer questions from Relay's documentation (12 short documents in `data/docs/`). Before choosing how to give the model that documentation, the team wants to know, for each strategy: **does the answer even reach the model, and how many tokens does that cost?**

You will compare:

| Strategy | What the model sees |
| --- | --- |
| `none` | Nothing but the question |
| `full` | All 12 documents |
| BM25, plain chunks | The top-k paragraphs by keyword relevance |
| BM25, titled chunks | The same, with each paragraph prefixed by its document's title |
| BM25, titled, expanded query | The same, after adding synonyms from a curated map to the question |

The questions come in three sets (`data/questions.jsonl`, field `type`):

- **keyword** (24): reuse the documents' own words.
- **paraphrase** (12): ask the way customers do. The synonym map in `data/synonyms.json` was written while reading these.
- **heldout** (10): paraphrases written after the synonym map was frozen. They show whether the map generalizes.

## Folder layout

```
L2.2-context-strategies/
├── data/
│   ├── docs/                ← 12 Relay documents
│   ├── questions.jsonl      ← 46 questions: keyword, paraphrase, heldout
│   └── synonyms.json        ← the curated synonym map
├── scripts/build_corpus.py  ← writes everything in data/ (deterministic)
├── starter/ctx/
│   ├── retrieval.py         ← TODO: tokenize, chunk_document, expand_query, BM25.score
│   ├── strategies.py        ← TODO: answer_in_context, reciprocal_rank
│   ├── report.py            ← provided: the comparison table (and optional live mode)
│   └── explain.py           ← provided: token-level explanation of one retrieval
├── solution/ctx/            ← reference solution
├── templates/context-findings.md
├── tests/
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Run pytest from this lab's folder.

## What you will practise

- Separating **retrieval** (did the right text arrive?) from **generation** (did the model use it?).
- Implementing and inspecting a real ranking function (BM25) instead of treating retrieval as magic.
- Measuring recall, mean reciprocal rank and context cost together.
- Recognizing **evaluation leakage**: a fix tuned on the questions it is scored on.

## Steps

### 1. Read the corpus (20 min)

Read all 12 documents and the 46 questions. Predict which paraphrased questions keyword search will miss, and why.

### 2. Implement retrieval (90 min)

Implement the TODOs in `starter/ctx/retrieval.py` (`tokenize`, `chunk_document`, `expand_query`, `BM25.score`) and `starter/ctx/strategies.py` (`answer_in_context`, `reciprocal_rank`). The BM25 formula is in the class docstring; `tests/test_retrieval.py` checks it against a hand-computed value.

```bash
python -m pytest -q
```

### 3. Run the comparison (10 min)

```bash
cd starter
python -m ctx.report --data ../data > ../evidence/context-strategies.md
python -m ctx.explain --data ../data --question P05      # why one paraphrase ranks badly
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead. PowerShell 7 writes UTF-8.

### 4. Analyse (45 min)

Copy `templates/context-findings.md` to `evidence/` and answer, with numbers:

1. What does `full` cost per question compared with BM25 top-3, and when would `full` stop being possible?
2. How much worse is keyword retrieval on paraphrased questions than on keyword questions?
3. Did title prefixes help? On which set, and at which k?
4. The expanded query reaches 100% on the paraphrase set. What does it reach on the held-out set, and why is the first number misleading?
5. For two paraphrased questions BM25 misses at k=3, explain the miss by looking at the tokens. `python -m ctx.explain --data ../data --question <id>` (from `starter/`) prints them.
6. Several differences in the table are one or two questions. Compute a Wilson interval for at least one of them (for example 8 of 10 against 7 of 10) and say what you can and cannot conclude.

### 5. Live run (optional, 20 min, costs money)

```bash
cd starter
python -m ctx.report --data ../data --live claude-haiku-5-5 >> ../evidence/context-strategies.md
```

Compare "answer reaches the model" with "answer contains the expected phrase". The gap between them is the generation side of the problem. Live mode uses titled chunks at top-3 for the `bm25` row, and counts refusals, truncated answers and API errors separately.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/context-strategies.md` | The generated report (and the live table, if run) |
| `evidence/context-findings.md` | All five questions answered with numbers, and a recommendation |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> On keyword questions, BM25 top-1 puts the answer in front of the model 100% of the time for about 49 tokens of context. On paraphrased questions top-1 manages 6 of 12 with titled chunks and 5 of 12 without, a one-question difference well inside the noise. The synonym map lifts paraphrase recall at k=3 from 58% to 100%, but on the held-out set it changes nothing (90% with or without), because it was tuned on the questions it was scored on. Sending all 12 documents always includes the answer, at 1,531 tokens per question: about fourteen times plain BM25 top-3 (109 tokens on the paraphrased set). Recommendation: plain chunks at top-3, which match titled chunks on the held-out set (90%) with a better MRR@3 (0.85 against 0.80) and fewer tokens. Treat titles and the synonym map as hypotheses for a larger held-out set, alongside embedding and hybrid retrieval.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| BM25 test off slightly | Use `ln(1 + (N − df + 0.5) / (df + 0.5))` for idf, and count repeated query terms once. |
| Chunk IDs differ | Number paragraphs from 1 and skip the `# Title` line. |
| Paraphrase recall higher than the reference | Your tokenizer stems or lower-cases differently; follow the docstring exactly. |
| A hit is counted from the wrong document | `answer_in_context` must require the passage to come from the question's `source` document. |

## Cleanup

Offline: nothing. Live: no resources created; check your usage page.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Implementation | 3 | All tests pass against `starter/` |
| Cost and recall trade-off | 2 | Quantified, including when `full` stops scaling, with small-sample differences treated as noise |
| Leakage | 3 | Explains why tuned results overstate quality, using the held-out numbers |
| Recommendation | 2 | A strategy, the evidence for it, and what to measure next |

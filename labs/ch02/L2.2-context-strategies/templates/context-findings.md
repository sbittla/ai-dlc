# Context Strategy Findings — Relay Support Assistant

**Author:**
**Date:**

## 1. Cost of sending everything

Tokens per question for `full` vs BM25 top-3, and the corpus size at which `full` stops fitting or stops being affordable. State your assumptions (context window, price, questions per day).

## 2. Keyword vs paraphrased questions

| Setting | Keyword | Paraphrase | Held-out |
| --- | ---: | ---: | ---: |
| BM25 top-1, plain | | | |
| BM25 top-3, titled | | | |
| BM25 top-3, titled, expanded | | | |

## 3. Did titles help?

## 4. Leakage

Why the expanded-query result on the paraphrase set overstates quality.

## 5. Two misses, explained

For each: the question, its tokens, the chunk that holds the answer, its tokens, and why BM25 ranked it low.

## Recommendation

Which strategy now, what you would evaluate next, and the held-out evidence that would change your mind.

## AI-use disclosure

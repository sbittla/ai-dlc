# Chapter 2 — Answers and Marking Notes

## Recall

**1. Invented settings.** A model generates the most probable continuation of its context, token by token, with no step that checks facts. Pretraining taught it the style of configuration keys, so a key "in Relay's style" is a probable continuation even if Relay has no such key. Instruction tuning rewards confident, helpful answers, so it rarely says "that setting does not exist" unless the context shows it. Full marks need all three: next-token generation, learned style without the specific fact, and the helpfulness bias.

**2. Why validate schema-guaranteed output.** Any three of:
- Not every model, provider or deployment supports constrained output, and code outlives configuration.
- A schema guarantees shape, not truth.
- Responses can be refused, truncated or empty.
- Defence in depth: a provider change or bug should fail loudly in your code, not silently downstream.

**3. Retrieval vs generation failure.** Retrieval failure: the passage containing the answer never reached the model. Generation failure: it reached the model, and the model answered wrongly anyway. Tell them apart by logging the retrieved chunks with each answer and checking whether the answer passage was among them. Recall@k measures retrieval alone, with no model involved.

**4. Why Wilson.** The simple interval can extend below 0 or above 1, collapses to zero width at 0% or 100%, and is inaccurate for small n. Model evaluations often have small n and accuracies near the extremes. The Wilson interval stays within [0, 1] and has better coverage in those conditions.

## Apply

**5. Two models, 50 calls each.**
- 45 of 50 (90%): Wilson 95% interval ≈ **78.6% to 95.7%**.
- 40 of 50 (80%): Wilson 95% interval ≈ **67.0% to 88.8%**.

The intervals overlap substantially, so you cannot conclude the first model is better on this task. Next steps: enlarge the dataset (more distinct inputs, not only more repeats), look at *which* inputs each model gets wrong (paired comparison on the same inputs is more powerful than comparing two proportions), and check whether the failures matter differently. Full marks need the intervals, the "cannot conclude" judgement, and at least one sound next step.

**6. Cost per correct answer.**
- A: $0.002 ÷ 0.90 ≈ **$0.00222**.
- B: $0.0002 ÷ 0.60 ≈ **$0.00033**, about 6.7 times cheaper per correct answer.

Choose A where errors are expensive or hard to catch, for example classifying security incidents or drafting customer-facing replies sent without review. Choose B where errors are cheap, caught downstream, or can be retried or escalated, for example suggesting tags a person confirms, or a first pass whose low-confidence or invalid results go to A. Deduct marks for choosing on cost per call alone.

**7. The "find the braces" parser.** It hides every response that wraps JSON in prose or fences, so the measured failure rate is too low. It can also return valid but wrong output. Example:

```text
{"category": "bug", "priority": "P1", "team": "platform"} Correction: on reflection this is P4.
```

The extraction returns the first object, which is valid and says P1, while the model's final answer was P4. Another example: two JSON objects in one response, where the slice spans both and fails to parse, or an example object quoted before the real answer.

Rewritten policy: parse the whole response strictly; on failure, record the failure kind, retry once with the same prompt, then route to the fallback path (a person, or a stronger model). Never extract, strip or repair. Count every failure in monitoring.

## Design

**8. Evaluating email reply drafts.** Look for:
- **Dataset:** at least 100 real (redacted) emails across categories, with a defined share of hard cases (angry customers, ambiguous requests, multiple questions in one email) and adversarial cases (injection attempts, requests for other customers' data). Synthetic data only until data-handling terms are confirmed.
- **Scoring:** a rubric with separate criteria (factually correct against the knowledge base, answers every question, tone, no policy violations, no data leakage), scored by trained reviewers. Model-graded scoring only after it is calibrated against human scores (Chapter 7).
- **Repeats:** at least 3 per email, with consistency reported.
- **Failure modes counted:** hallucinated facts, missed questions, policy violations, leaked data, refusals, format failures.
- **Decision rule:** a minimum on every safety criterion that is a hard gate, then cost per acceptable draft. Prefer the model whose interval on the main criterion is clearly higher; if intervals overlap, choose on safety and cost.

**9. Retrieval for 4,000 documents with admin-only content.** Look for:
- **Pipeline:** chunking with document titles or section headers; hybrid retrieval (BM25 plus embeddings) with reranking; metadata on every chunk (document ID, version, indexed date, access level).
- **Access control:** filter by the requesting user's permissions *before* chunks enter the context, ideally inside the retrieval query. Post-generation filtering is wrong, because the model has already read the text. Test it with non-admin questions designed to retrieve admin-only text.
- **Evaluation:** 50+ questions with known answer passages, written in real user phrasing; a held-out set nobody tunes on; recall@k and MRR tracked per release; answer accuracy and citation support measured separately in live runs.
- **Freshness:** re-index on document change, and alert on stale chunks.
- Full marks need the access-control placement and the held-out set.

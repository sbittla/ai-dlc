# ADR-042 — Triage routes on difficulty, with token limits and timeouts per route, judged by cost per correct triage

Status: accepted
Date: 2027-02-17
Decided by: sam.o (architect of record)
Reviewed by: lena.k (product), tomas.b (support), aisha.r (security)
Links: ESC-N01, ESC-N02, D3, CON-4, CON-6
Related: ADR-007, ADR-024, ADR-040, ADR-043
Revisit when: the canary's weekly labelled sample disagrees with the lab's ranking; a model or prompt version
changes; or provider prices change (recalibrate the table first). Review by 2027-05-17 in any case.
Supersedes: the 6 January 2027 switch of all triage to the reasoning model (Chapter 17's incident; reverted
on 9 February).

## Context

On 6 January 2027 triage moved from `sim-large` to a reasoning model after Chapter 7's gate passed it: it got
6.3 points more held-out tickets right on the first call (+3.6 to +9.7, McNemar p = 0.004), and the gate's
cost warning (2.36 times per correct answer) was accepted. The gate scored one call with no clock. In the
worker, the reasoning model's long answers met the 10-second timeout: calls were billed and thrown away,
retried, and 20 of 600 replayed triages went to a person. Lab 17.2's replay under the worker's rules shows
production quality +3.0 points (-0.3 to +6.9, p = 0.581: no clear change), cost per correct triage 3.00
times, and p95 time to a suggestion 26.6 s against 3.5 s. Nobody watched cost per success, so it ran a month.

## Options considered

### Option A — Route predicted-hard tickets to the reasoning model with a 1,100-token limit and a 30 s timeout; everything else to sim-large

### Option B — Return to sim-large for every ticket

### Option C — Keep the reasoning model for every ticket and raise the worker's timeout

## Decision

Option A, for a canary behind Chapter 7's gate once the merge notes below are in, with Option B as the rollback
(one configuration change). Until then production stays on Option B.

- `relay.routing` holds the routes: model, prompt, output-token limit (reasoning included) and timeout.
- The difficulty score is an assumption, not code in 4.28.0: Relay has no scorer. The route uses Chapter 7's
  router (Lab 7.1's naive Bayes scorecard over words and four style flags), trained on dev, at the highest
  threshold that catches 80% of hard dev tickets out of fold (0.747956); it sends 65.5% of held-out runs to
  the reasoning model. Packaging it with its weights and threshold as a versioned worker module is part of
  the worker merge note (owner priya.n), and it goes through Chapter 7's gate like a prompt.
- `route_problems` refuses a route whose token limit lets a call run past its timeout. The incident's route
  (2,048 tokens behind 10 s) fails it; Option A's hard route passes.
- A configuration is judged by cost per correct triage under the worker's rules, never by cost per call or
  per token, and the gate's record now includes that production replay.
- Merge note for the worker: `Worker` scores each ticket, takes its timeout from the route the policy chooses
  (`RoutePolicy.choose(score).timeout_s`) instead of one `timeout_s`, and records the route's model in the
  result. Apply it after Chapter 12's 4.26.0 changes to `runner.py` (the spotlighting envelope): score the
  unmarked text. Until then the hard route's 30 s timeout cannot be deployed, and the canary waits.

## Consequences

- Lab 17.2 (held-out, simulated): +3.8 points against sim-large (+1.7 to +6.6, 0 worse and 6 better, p = 0.031),
  no timeouts, no tickets to a person, cost per correct triage 2.00 times sim-large's, p95 time to a suggestion
  10.6 s. This illustrates the method; it is not evidence for the route. The reasoning model's accuracy was
  configured on the held-out split, and its reasoning lengths and output rate were chosen from four settings
  while the held-out results for B and C were in view. Only the canary's labelled sample counts as evidence.
- Suggestions still never change a task (D3, ESC-N01); a slower suggestion is a support cost, and ADR-040's
  30 s budget holds for this route.
- The triage prompt, about 427 tokens, is under the provider's 512-token cache minimum, so caching does not
  lower this cost; routing splits traffic across two models' caches if a longer prompt ever makes it apply.

## Rejected alternatives

### Option B — Return to sim-large for every ticket
Rejected because: it gives up the reasoning model on hard tickets without testing it on real ones; a canary costs about half a cent per correct triage.
Revisit if: the canary shows no gain on labelled production tickets; then Option B is the decision.

### Option C — Keep the reasoning model for every ticket and raise the worker's timeout
Rejected because: it pays three times sim-large's cost per correct triage for a production quality gain the replay cannot separate from zero, and slows every ticket.
Revisit if: a reasoning model's price falls to the large model's cost per correct triage, measured under the worker's rules.

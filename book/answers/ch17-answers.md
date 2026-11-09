# Chapter 17 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch17/L17.1-load-test-bottleneck/` (its `relay-repo/` and `solution/perflab/`) and `labs/ch17/L17.2-cost-per-success-routing/solution/costlab/`. They are locked by each lab's `tests/test_answers.py`. The triage models, their latency and the abuse traffic are simulated and configured; the load-test milliseconds were recorded on the author's laptop.

## Recall

**1. Coordinated omission.** A closed loop sends the next request only after the previous answer, so while the system stalls it sends nothing. The requests that real users would have sent during the stall, and their long waits, are never recorded: in Table 17.2 the closed loop records one slow sample out of 1,901 and reports a p99 of 1.0 ms for a one-second stall. Two ways avoid it: an open schedule with every request timed from its due time (p99 821.0 ms), or a correction that adds the missing samples for the expected interval (p99 801.0 ms). Full marks need the mechanism and both remedies.

**2. The four tests.**

| Test | Question | Relay's version |
| --- | --- | --- |
| Load | Does the expected load, with headroom, meet the budgets? | 140 requests a second, twice the busiest minute |
| Stress | Where does it stop meeting them, and how does it fail? | 280, 420 and 560 requests a second; the exact limiter's knee lies between 140 and 280 |
| Spike | Does a sudden rise get absorbed, and how fast does it recover? | The outage's 300 tickets in ten minutes, for the triage workers |
| Soak | What goes wrong with age or with data at a future size? | The queue table at a year's finished jobs, and the worker's claim |

Full marks need a question and a Relay example for each.

**3. Caching and `triage-v3.1`.** Its system prompt is about 427 tokens by the lab's estimate, under the 512-token minimum the provider documents for its current large models, so no prefix is ever cached and the saving is $0. Two things would change that: a longer stable prefix (more instructions, examples or reference text, which also costs more), or a model or provider with a lower minimum. Strong answers add that routing between two models splits the cache, and that the minimum and prices are dated assumptions to check.

**4. Quotas and rate limits.** A rate limit bounds how often a caller may ask; at 600 a minute one token can queue 36,000 paid triage calls an hour. A spend quota bounds what the asking may cost in a day. In Relay's design the user and workspace quotas bound how many tickets can be queued (one hard-route call's ceiling each, never settled), and the agent and feature quotas, which settle actual costs, bound the money. Refusals should raise an alert because a quota being reached is either abuse, which needs a token revoked, or real demand, which needs a limit raised; and a workspace limit refuses that workspace's real users too (Table 17.11). In 4.28.0 the ledger only counts refusals (`SpendQuota.refusal_counts`); the paging rule is ADR-043's proposed AL-009 for Chapter 16's alert rules, live only after the merge. Full marks need both halves, and strong answers note that the alert is not yet wired.

## Apply

**5. Four processes.** (a) Each of the other three processes can hold at most 9 unused leased counts, so a token can be refused early by at most (4 − 1) × 9 = 27 requests in a window: it may be held to 573. (b) 600 requests spread evenly is 150 per process, which is 15 leases of ten each, so 60 write transactions, 0.1 per request. The exact limiter would have issued 600. Lab 17.1's `tests/test_answers.py` runs both cases on the real limiter. Full marks need both numbers and the reason for (a).

**6. Cost per correct triage.** C's cost per ticket is $0.004543 × 1.003 = $0.004557, and dividing by the 90.8% correct gives $0.005018 per correct triage, as Table 17.8 shows. If the provider did not bill the calls the worker gave up on, B's cost per correct triage would fall from $0.007529 to $0.005397, 2.15 times A's instead of 3.00. So of B's excess over A, 2.00 times A's cost, 1.15 comes from the reasoning tokens themselves and 0.85 from paying for timed-out calls. Full marks need the arithmetic and the conclusion that a refund policy would not make B cheap.

**7. Workers for the outage.** Little's law gives busy workers as the arrival rate times the mean busy time: 31.8 / 60 × 2.354 = 1.25 workers with A, and 31.8 / 60 × 7.028 = 3.73 with B. ADR-040's two workers cover A's peak, as Table 17.6 confirms (p95 13.9 s). With B, two workers would fall behind by about 1.7 workers' worth of work for the whole ten minutes, the queue would grow, and the 30-second budget would fail. The new model needed twice as many workers as well as three times the money. Full marks need both estimates, the comparison with two workers, and the caveat that Little's law uses means and says nothing about percentiles during a growing queue.

## Design

**8. A load-test plan for the PostgreSQL adapter.** Strong plans:

- Keep the workload (`perf/workload.json`), the schedule and seed, and the budgets; add a journey only if the adapter changes one.
- Run on an environment like production: the database on its own instance over the network, two or more service tasks behind the real load balancer, and the client outside the service host. Record instance types, regions and versions.
- Measure inside the server: time in the application, in the limiter and in each query, and the database's own lock waits and commit latency.
- Run exact and leasing limiters interleaved, five runs each, at the test rate and in a stress sweep; then a soak at a year's table sizes.
- Decide in advance: if the exact limiter meets the p99 budget with at least twice the headroom of the stress knee, and its share of server time is small, leases are optional; otherwise keep them. Note that PostgreSQL's row locks make the limiter's contention per token rather than per database, so the result may differ from SQLite's.

Marking: workload and environment stated, server-side measurement, interleaved repeats with intervals, a stress and a soak, and a decision rule written before the runs.

**9. Spend controls for customer-facing triage.** Strong designs:

- Principals: the customer workspace (the main budget), each user or integration token in it, Relay's worker agent, and the feature as a whole; every limit per UTC day, in configuration.
- Limits from measured use: a percentile of real daily spend per workspace and per token over a month, times a headroom factor, reviewed monthly. Reservations use the route's ceiling, so the limits must be set in ceiling dollars.
- At a limit: queue nothing, answer 429 with Retry-After, show the customer that AI triage is paused for today, and keep the tickets for people; never guess a label.
- A daily monitor of spend per suggestion per workspace (labels arrive late), a weekly check of cost per correct triage against the approved baseline, and a check of total spend against a ceiling, paging the on-call.
- Against twenty stolen tokens: per-token limits well below the workspace's share, so one workspace's tokens cannot use it up together quickly; anomaly detection on new tokens' volume (Chapter 14's detection rules); a separate, smaller limit for tokens created recently; and fast revocation. Accept that the workspace limit is the backstop, and say so to the customer.

Marking: all four kinds of principal, a method for setting limits, the refusal behaviour, the monitor, and a credible answer to the collateral problem.

# ADR-027 — The spec-to-PR helper's pilot is a workflow with one bounded agent step (the routed design)

Status: accepted
Date: 2027-01-22
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), lena.k (product)
Links: CON-1, ADR-024, ADR-025, ADR-026, Chapter 7 (regression gate), Chapter 9 (implementation loop)
Revisit when: the live rerun on real tasks reports; or held-out results change after a model or prompt change; or the escalation rate rises above half of runs. Review by 2027-07-22 in any case.

## Context

The helper turns an approved task (a spec section, its file list and its approved tests) into a draft pull request, or hands the task back. Lab 10.1 built it four ways on Relay's runtime and ran each on 30 dev and 90 held-out tasks, three times each, with a simulated model whose behaviour is configured, not measured. Budgets were set from dev runs. The routed design's review call was added after the dev runs, where the routed design without it opened 11 wrong pull requests in 90 runs against 5 to 8 for the others: a small difference, taken as a hypothesis. The held-out split was run once, afterwards.

## Options considered

### Option A — A deterministic workflow

### Option B — A single agent

### Option C — A supervisor with four agents (planner, coder, tester, reviewer)

### Option D — Routed: the workflow first, with a review call; the single agent only when the workflow's three attempts fail

## Decision

Option D, for the pilot, as a judgement rather than a measured win. On the held-out split (simulated), the workflow alone fails Chapter 7's gate against the single agent (-5.9 points, -10.0 to -2.6). The other three designs cannot be separated on quality. The routed design's success difference against the single agent is +4.1 points (+0.7 to +7.8), but McNemar on majority outcomes sees 1 task worse and 4 better (p = 0.375), the shared draws narrow the interval, and part of the single agent's loss is six runs stopped by its budget. Its wrong pull requests differ by -4.1 points at the run level (-8.1 to -0.4), but by majority it has more tasks with a wrong pull request (b = 1, c = 2, p = 1.0), and on dev it had more (8 against 6). The reviewer's benefit is a configured catch rate, the same in both designs that review.

What decides it is structure. Two thirds of the routed design's runs are a fixed, testable workflow, and an agent with search, reading content Relay did not write, runs on only 91 of 270 runs (33.7%). It makes 7.1 model calls per run against 11.4. The cost is 18.8% more per run than the single agent ($0.168 against $0.142) and a slower 90th percentile (220 s against 137 s). The multi-agent design costs 71.5% more per run than the single agent, needs five identities, and is not more often right.

## Consequences

- The helper registers one identity, `spec-to-pr-helper`, with one Relay scope, delegation from priya.n or sam.o, and its own GitHub App, `relay-spec-to-pr` (ADR-020, ADR-025).
- Every pull request needs its requester's authenticated approval of the exact diff the boundary computed (ADR-026). A code owner other than the requester reviews it, and the helper never merges.
- Five of the 91 escalated held-out runs stopped at the money limit. Recalibrate the routed budget with escalated dev runs before the helper leaves its pilot.
- The comparison is simulated. Before the helper is used beyond a pilot, rerun Lab 10.1's comparison on real tasks with the live adapter, sized for the two questions that decide the design: how often the workflow's context misses a file, and how often each design opens a wrong pull request. If the routed design shows no advantage there, adopt the single agent, which is simpler and cheaper per success.

## Rejected alternatives

### Option A — A deterministic workflow
Rejected because: it fails Chapter 7's non-inferiority margin against the single agent, mostly on tasks that need an unlisted file it cannot find.
Revisit if: task file lists become complete enough that cross-file tasks disappear; it stays as the routed design's first stage.

### Option B — A single agent
Rejected for the pilot because: the evidence does not separate it from the routed design on quality, and it runs an agent with search on every task.
Revisit if: the live rerun shows no advantage for the routed design; then the single agent's lower cost per success ($0.206 against $0.231) decides.

### Option C — A supervisor with four agents (planner, coder, tester, reviewer)
Rejected because: it is not more often right, costs much more per run, needs five identities, and its reviewer is one model call that the routed design takes as a workflow step.
Revisit if: tasks grow large enough to need parallel workers on separate files (Chapter 9's partitions).

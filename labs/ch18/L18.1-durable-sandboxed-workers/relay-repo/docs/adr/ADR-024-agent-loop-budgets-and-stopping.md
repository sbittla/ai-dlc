# ADR-024 — Every agent run has a budget and stopping conditions decided by code

Status: accepted
Date: 2027-01-19
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: CON-1, ADR-020, ADR-022, Chapter 9 (stop signals)
Revisit when: an agent's work needs a run longer than one working session; or a provider offers enforced spend limits per agent identity; or more than 5% of held-out runs stop at a budget. Review by 2028-01-19 in any case.

## Context

On 14 January 2027 a five-agent prototype of the spec-to-PR helper ran for six hours on one task and spent about $1,800 (Lab 10.1's replay, from assumed token sizes and processing rate: $1,800.27 over 359.9 minutes, 608 model calls). Its only stopping condition was its own reviewer's approval, which never came; GitHub Actions' job limit ended it. Nothing in Relay limited what an agent run could spend, how many steps it could take, or how often it could repeat the same failure.

## Options considered

### Option A — A budget and stop rules in Relay's runtime, checked before every step

### Option B — A spend alert on the model provider's account

### Option C — Ask the model to stop when it is not making progress

## Decision

Option A. `relay.agents.budget` gives every run a `Budget` (steps, model calls, money, wall time) and a `Meter` that records use by actor. `Meter.check` refuses a step once any limit is reached, and `Meter.admit` refuses a model call whose upper estimate would cross the money limit. The loop computes that estimate itself, from the request's size and output allowance, and counts any call that costs more (`overruns`). `relay.agents.loop.stop_reason` stops a run before each step for a budget, for the same failure signature seen three times (Chapter 9's stop signal), or for six steps that observed nothing new. A model's "finish" is accepted only if a done check agrees. Budgets are set per design from dev runs: 1.5 times the 95th percentile of successful runs.

## Consequences

- A runaway loop costs at most its budget, plus the overshoot of one step's duration on the time limit. The incident's loop, replayed with the multi-agent design's budget, stops after 11 calls and $0.604; with the repeated-failure rule alone it stops after 13 calls.
- The meter's totals are part of the run's checkpoint (ADR-026), so resuming a run can never reset its budget.
- Budgets set from dev runs miss rare paths. In Lab 10.1's held-out runs, 5 of the routed design's 91 escalated runs stopped at the money limit; the budget will be recalibrated with escalated runs included.
- The upper estimate assumes a call writes its whole output allowance, so a run usually stops a little before its money limit.

## Rejected alternatives

### Option B — A spend alert on the model provider's account
Rejected because: an alert tells a person after the money is spent, works per account rather than per run, and fired on nothing in the incident.
Revisit if: never as the only control; it stays useful as a second layer.

### Option C — Ask the model to stop when it is not making progress
Rejected because: the model that is looping is the one deciding whether it is looping; the incident's agents each acted as if the next round would succeed.
Revisit if: never for limits; the instruction stays in prompts as advice.

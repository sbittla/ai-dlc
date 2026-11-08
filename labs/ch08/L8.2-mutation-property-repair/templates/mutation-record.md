# Mutation record

Policy: relay-mutation-v1 · Modules: rules, evaluate, hours (and delivery for Relay's suite) · Author: <name> · Reviewer: <name> · Date: <YYYY-MM-DD>

## 1. Before and after

| Suite | Line coverage | Mutants | Killed | Score | Score with no equivalence claims | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Agent's suite | | | | | | |
| Your repair | | | | | | |
| Relay 4.20.0's suite | | | | | | |

## 2. What the agent's suite missed

Group its survivors into kinds (for example: refusal codes never asserted, boundaries tested only from inside, expected values computed by the code, data no test reads). Give one mutant of each kind and the test that now kills it.

## 3. Properties

For each property: what it states, its generator and number of runs, its oracle, and why that oracle is independent of the code.

## 4. Every survivor decided

| Mutant | Decision (test added, or equivalent) | Input tried, or the test's name | Reviewer |
| --- | --- | --- | --- |

## 5. Limits of the score

What would this score not notice? Consider: the operator set; mutants in data tables; behaviour no operator changes (a missing feature); and the cost of running mutation testing on every change.

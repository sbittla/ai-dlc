# Architecture review record — Relay 4.19.0

**Author:**
**Architect of record (approver):** (a named person, not the author and never an agent)
**Date:**

## 1. Drivers

Which drivers in `data/drivers.json` decide this architecture, and which are not architecture-significant? Is any
weight one you would change? Say why, with the driver ID.

## 2. Scores and sensitivity

Paste the totals, the ranking and the sensitivity lines from `archscore.report score`. Which scores are you least
sure of? Change each to the value you find most plausible and report whether the ranking moves.

## 3. What the scores cannot show

Name at least three things the weighted total does not capture (for example: the cost of migrating later,
how the team's skills match each option, risks correlated across drivers). For each, say how you judged it.

## 4. Structure

Deployable units, databases, trust boundaries and the components a step needs, for each option. Which number
surprised you, and why?

## 5. Threat models

For each option: boundaries, threats, and how many controls have evidence today. Which threat would you test first?
Why is comparing a built option's threat model with an unbuilt one's misleading, and what did you do about it?

## 6. Decision record

The path of your ADR, the checker's result (`--gate` exit status), and the rejected alternatives with their
"revisit if" conditions.

## 7. The running service

The output of `curl` (or `Invoke-RestMethod`) for `/healthz`, one triage job submitted twice with the same
Idempotency-Key, and the job's suggestion after the worker ran. What did `applies_to_task` say, and why?

## 8. AI-use disclosure

What did an agent or assistant draft (options, scores, ADR text, threat models)? How did you verify each part?
Which of its claims did you reject?

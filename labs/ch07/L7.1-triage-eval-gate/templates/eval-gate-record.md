# Eval Gate Record — Relay Ticket Triage

**Change:** (pull request or ticket)
**Date:**
**Author of record:**
**Reviewer:**

## What changed

| Item | Baseline | Candidate |
| --- | --- | --- |
| Model (exact ID, or "simulated") | | |
| Prompt version | | |
| Tools or retrieval changed? | | |

## Evaluation

| Item | Value |
| --- | --- |
| Dataset name and version | |
| Dataset hash (from the gate's `dataset` rule) | |
| Split and size | |
| Runs per ticket | |
| Gate policy | |
| Live or simulated | |
| Spend (live only) | |

## Gate result

Paste the gate's rule table. Then answer:

1. Decision (PASS or FAIL), and the rules that decided it.
2. The overall paired difference and its interval. Is it an improvement, a regression, or inside the noise?
3. Every warning, and why you accept it or not. A warning needs a named reviewer's acknowledgement.
4. Which slices are too small to read on their own? Quote their n.
5. What the leakage check found.

## Decision

Merge, hold or reject, and why. If the candidate is a model upgrade, state the rollout step (shadow, canary or full) and what online measurement will confirm it.

## What would change this decision

The measurements, slices, prices or events that would make you re-run the gate.

## AI-use disclosure

What an AI assistant produced in this lab, and how you verified it.

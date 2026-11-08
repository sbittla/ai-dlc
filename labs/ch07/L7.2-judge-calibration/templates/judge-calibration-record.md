# Judge Calibration Record — Relay Support Assistant

**Date:**
**Owner:**
**Judge (model ID, or "simulated") and prompt version:**
**Dataset name and version:**

## What the judge would replace

Which human labelling task, how many items per release, and what a wrong judgement costs. Say which error is worse here: a false pass or a false fail.

## Calibration (used to choose the judge prompt)

| Measure | judge-v1 | judge-v2 |
| --- | ---: | ---: |
| Answers | | |
| Accuracy | | |
| Cohen's kappa (95%) | | |
| False-pass rate | | |

Which prompt did you choose, and why? Which differences are too small to trust on this split?

## Held-out decision

Paste the `decide` report for the chosen judge. For each failed check, say what you would change and how you would re-test it without tuning on the held-out split.

## Bias probes

| Probe | Value | n | Within policy? |
| --- | ---: | ---: | --- |
| Verbosity gap | | | |
| Self-preference gap | | | |
| First-position rate | | | |
| Swap consistency | | | |

## Decision and controls

What the judge may do from now on, what stays with humans, the audit sample, and what triggers recalibration.

## AI-use disclosure

What an AI assistant produced in this lab, and how you verified it.

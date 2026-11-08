# Fitness-function review — Relay 4.19.0

**Author:**
**Reviewed by:** (a person who is not the author)
**Date:**

## 1. Rules and the decisions they protect

For each rule FF001–FF006 and each rule you added: the ADR it enforces, and the sentence in that ADR it makes
checkable. Which consequence of ADR-007 has no rule, and why?

## 2. Seeded results

Paste the `--seeded` table. For each miss, say why the tool cannot see it and what other control covers it
(review, a runtime check, a sandbox with no network, a test).

## 3. Your own seeded violation

Describe the violation you added, the rule that catches it (or why none can), and the gate's exit status.

## 4. Flagged by design

V10 is flagged although nothing is imported at run time. Keep the rule as it is, or change it? Give the reason
in terms of what the rule is for.

## 5. In CI

Where the gate runs (job name), whether it is a required status check, who owns the rules file, and how a rule
is changed (by whom, with which review). What stops an agent from editing the rules to make its change pass?

## 6. AI-use disclosure

What did an agent produce, and how did you verify it?

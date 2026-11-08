# Chapter 7 — Answers and Marking Notes

Arithmetic in Apply answers was checked by running Lab 7.1's `stats.mcnemar_exact` and `stats.paired_sample_size`, and Lab 7.2's `metrics.confusion` and `metrics.cohen_kappa`, on the stated numbers.

## Recall

**1. Evaluations and unit tests.** From Table 7.1, any four differences with their requirement:
- One case's result can change between runs → repeat runs.
- "Green" is a rate clearing a threshold, not every case passing → a written threshold and intervals.
- Cases represent traffic, with slices, rather than isolating one behaviour → production samples and slice reporting.
- Expected results are labelled by people who sometimes disagree → a labelling guideline and measured labeller agreement.
- Runs cost money and minutes → a budget and a spend ceiling.

The same: both state what correct means, run on every change, and block the merge on failure. Full marks need the requirement for each difference, not only the difference.

**2. Families.** A family is a group of cases sharing one underlying input, such as one customer problem written several ways, with one label. If a family crosses the split, anything tuned on dev has effectively seen held-out cases, so held-out scores measure memory (evaluation leakage, Chapter 2). Lab 7.1 measured it: a row split put 37 families on both sides and gave 47 of 200 held-out tickets a near-duplicate in dev (none with the family split). The router's held-out hard recall rose from 88.4% to 96.9%, an inflation of 8.5 points that is a measurement, not a configured effect.

**3. Judge biases.**

| Bias | Probe | Mitigation (any one) |
| --- | --- | --- |
| Position | Judge each pair in both orders; measure swap consistency and first-position rate | Judge both orders and treat disagreement as a tie for a person |
| Verbosity | Compare false passes on long wrong answers with short wrong answers | Reference answer; rubric that says length does not count |
| Self-preference | Compare false passes on wrong answers from the judge's own family with another family's | Use a judge from a different family than the outputs it grades |

**4. Kappa of 0 at 90% agreement.** Kappa subtracts the agreement expected by chance. If one rater says "pass" on all 10 items and the other on 9, they agree on 9 of 10, but chance agreement is 0.9 × 1.0 + 0.1 × 0 = 0.9, so kappa = (0.9 − 0.9) / (1 − 0.9) = 0. Agreement that comes only from both raters favouring one label tells you nothing about their judgement.

## Apply

**5. McNemar and the regression rule.** n = 14 + 5 = 19 discordant tickets, k = min = 5. The lower tail is (1 + 19 + 171 + 969 + 3,876 + 11,628) / 2¹⁹ = 16,664 / 524,288 = 0.0318, so the two-sided p ≈ **0.064**. It is not significant at 5%, though 14 against 5 leans clearly towards a loss.

Regression rule: the upper bound (+0.2) is not below 0, so not "worse beyond noise". The lower bound (−6.1) is below −5, so **FAIL: a drop larger than the margin cannot be ruled out**. Full marks need the p-value, the rule's second branch named, and a next step: more held-out tickets, or a reason to accept a wider margin written into the policy before re-running. Deduct for "passes because p > 0.05".

**6. Judge on 200 answers.**
- Accuracy = (90 + 88) / 200 = **89.0%**.
- p_o = 0.89. The judge passes 102 of 200 (0.51); humans pass 100 of 200 (0.50). p_e = 0.51 × 0.50 + 0.49 × 0.50 = 0.50. Kappa = (0.89 − 0.50) / 0.50 = **0.78**.
- False-pass rate = 12 / (12 + 88) = **12.0%**.

Checks you can apply: items (200 ≥ 100, passes) and false pass (12% > 10%, **fails**). The kappa check needs the interval's lower bound, which needs the item-level data for a bootstrap; the human-gap check needs the labellers' kappa; the bias checks need the probe groups. The judge fails single grading on false passes alone. Good answers note that kappa 0.78 looks respectable and still hides the error that matters most for a gate.

**7. Sample size.** With ψ = 0.10, two-sided 5% (z = 1.960) and 80% power (z = 0.842):
- δ = 0.05: (1.960 × √0.10 + 0.842 × √0.0975)² / 0.0025 = **312 tickets**.
- δ = 0.10: (1.960 × √0.10 + 0.842 × √0.09)² / 0.01 = **77 tickets**.

A 20-ticket slice cannot reliably detect even a 10-point difference at this disagreement rate, so a slice result inside the noise is not evidence of no change. That is why Relay's slice rules fail only on an interval entirely below zero and otherwise warn, and why slices that matter need more cases.

## Design

**8. Reply-drafting suite.** Look for:
- **Dataset:** production tickets (redacted, or synthetic until data terms are confirmed) with agreed reference replies; slices for ticket kind, language, plan and tone; adversarial cases (injections, requests for other customers' data); at least 100 held-out cases split by family; a manifest with version and hash.
- **Scoring:** assertions where possible (no data from another workspace, links resolve, required facts present); rubric grading for factual agreement with the knowledge base and for completeness; pairwise only for style questions.
- **Judge calibration:** at least 100 human-labelled drafts, kappa with interval, false passes, the three bias probes, a written decision rule on held-out data, a 10% human audit sample.
- **Gate:** paired comparison with repeats; a margin chosen for the business risk; absolute limits for data leakage and injection; slice rules; cost warning.
- **Online:** weekly sample labelled by support leads; edits the human agents make to drafts tracked as a signal; new failure kinds added to dev.
Full marks need an absolute rule for leakage of other customers' data and a judge calibrated before it gates.

**9. Upgrade plan.** Look for the playbook's steps in order: offline gate (done: fails the German slice, −25.0 points on 20 tickets, interval −43.3 to −8.3); study the failure on dev German tickets only; re-tune the prompt on dev and re-gate; shadow; canary with online evaluation; rollback by configuration. A split rollout routes by language: English and Spanish to the new model, German to the old, each route gated separately on its own slice with enough tickets (Equation 7.3). Costs: two models to operate and evaluate, a language detector that itself needs an evaluation, and a deadline set by the old model's retirement, which must be in the plan. Deduct for shipping on the overall +2.2 points, whose interval includes zero.

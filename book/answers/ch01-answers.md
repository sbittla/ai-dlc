# Chapter 1 — Answers and Marking Notes

## Recall

**1. Four forces.** Handoffs, queues, batch size, feedback latency. Accept any concrete example per force: a design passed from architect to developer (handoff); a pull request waiting for review (queue); a release bundling three weeks of changes (batch size); learning about a defect from a customer a month later (feedback latency).

**2. Little's Law.** L = λW. For a review queue: L is the average number of changes waiting for review; λ is the rate at which changes arrive for review (for example, changes per hour); W is the average time a change waits. It relates *averages*: the product of the mean arrival rate and the mean wait equals the mean number waiting. A median wait would give the wrong L, because long waits (which skew the mean upward) contribute their full time to the queue. Full marks also note that it assumes a stable system, where arrivals and departures roughly balance over the period.

**3. DORA metrics, in DORA's 2024 grouping.** Throughput: change lead time, deployment frequency, failed deployment recovery time. Instability: change fail rate, rework rate. Accept "stability" for "instability". If a learner places recovery time under stability with a note that earlier DORA reports did so, award full marks.

**4. Evidence.** An artifact; a check that ran, with its date and inputs; and a named person who accepted the result.

## Apply

**5.1 Flow efficiency.**
- Before: active = 6 + 3 = 9 h; lead time 60 h; flow efficiency = 9 ÷ 60 = **15%**.
- After halving coding: coding 3 h; lead time 57 h; active = 3 + 3 = 6 h; flow efficiency = 6 ÷ 57 ≈ **10.5%**.
- Interpretation: lead time improves by only 5% (3 of 60 hours) because 51 hours are waiting. Flow efficiency *falls*, so the process is now even more dominated by queues. The limit is waiting, not coding. Full marks require this interpretation, not only the arithmetic.

**5.2 Queue arithmetic.**
- Little's Law: L = 3 changes per hour × 2 hours = **6 changes waiting on average**.
- Utilization factor ρ ÷ (1 − ρ): at 60%, 0.6 ÷ 0.4 = 1.5; at 90%, 0.9 ÷ 0.1 = 9. It grows by a factor of **6**. Full marks note that this is only the utilization term; variability and service time also matter, and Kingman's formula is a single-server approximation.

**6. Autonomy tiers.** Model answer, consistent with Figure 1.2. Accept other tiers when the reasoning applies the four questions and the chapter's three rules: at most T2 when an agent acts on untrusted content, no T4 for irreversible or sensitive tasks, and T0–T1 when all four risk factors are present.

| Task | Tier | Reasoning |
| --- | --- | --- |
| (a) Rename a private function across a repository | T2; T4 possible with strong tests and a narrow policy | Reversible, contained, not sensitive, verifiable by compiler and tests |
| (b) Rotate a production database password | T1 for the agent, a person executes; T3 if automated, with each step approved | Touches a secret and can cause an outage, so never T4; it is not irreversible *and* wide *and* unverifiable all at once, so per-action approval (T3) is allowed |
| (c) Draft a reply to a support ticket | T1 | The ticket is untrusted input, so the path is capped at T2 and continues. Sending is irreversible and the content may contain personal data, so the lower tier applies: the agent drafts, a person sends |
| (d) Update a dependency to a new patch version | T2 for an agent | Reversible and verifiable, but the agent handles third-party code, which is untrusted input, so it stays at T2 with a person merging. Full marks also note the chapter's alternative: a deterministic bot with no model interpreting package contents may auto-merge patch updates when every check passes, under an audit log and kill switch. That is a policy, not an agent at T4 |
| (e) Delete stale feature flags from production configuration | T2 to prepare the change, T3 to apply it | Production configuration with a potentially wide blast radius; the agent identifies and drafts, a person approves application |

**7. Reporting recovery time honestly.** Model answer: "Median recovery time fell from 5.1 to 3.2 hours, but mean recovery time rose from 4.6 to 5.3 hours. With only three failures in Q1 and five in Q2, the data cannot distinguish any change; we will report recovery time once a period has at least [team sets N] failures, and list each incident's recovery time individually until then." Deduct marks for "improved", and for "within normal variation" without a test.

## Design

**8. Pilot design.** Look for:
- A concurrent comparison group doing comparable work, not only a before-and-after comparison.
- Task assignment that prevents selection bias: random assignment of backlog items, or stratification by size and type before assignment.
- A primary *outcome* metric (feature change lead time is the natural choice) with a written definition.
- Two guardrails with numeric thresholds **and windows**, for example change fail rate ≤ 15% and rework rate ≤ 10% over rolling three-month windows with a minimum event count, plus a security guardrail. Strong answers cite the chapter's evidence that monthly windows raise false alarms (February) at Relay's volumes.
- Acknowledgement that four weeks yields few deployments and failures, so stability guardrails may need a longer window or pooled data.
- Explicit decision rules: stop if a guardrail trips; continue if lead time improves but evidence is weak; expand only if lead time improves and guardrails hold.
- A named decision owner.

**9. One number for the CEO.** Strong answers:
- Explain Goodhart's law with an example from the chapter (cost per accepted change).
- Propose a small balanced set: one throughput metric (lead time), one stability metric (change fail rate or rework rate), one cost metric, and one experience signal (developer satisfaction trend).
- Give the CEO something simple, such as a monthly status of "faster and as safe", "faster but less safe" or "no change", backed by the set.
- Refuse activity counts as the headline.

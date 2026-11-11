# Chapter 20 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch20/L20.1-maturity-operating-model-roi/solution/adoption/` and `labs/ch20/L20.2-controlled-adoption-experiment/solution/experiment/`. They are locked by each lab's `tests/test_answers.py` and `tests/test_golden.py`. The company, its four other teams and all their data are fictional; the pilot's effects are configured.

## Recall

**1. Evidence, not opinion; no averages.** Opinion records what a team believes about itself, and the people assessed are the ones giving it, so it cannot separate a strong team from a confident one. The scorer counts only admissible items: of an accepted type, with a reference and an owner, dated on or before the assessment, fresh enough, and meeting the criterion's threshold. Two assessors agree because the level is a function of the register alone; when they disagree, the disagreement is about an item, and an item can be checked.

There is no average because an average hides the dimension most likely to fail; the report names each team's lowest dimension and the criterion that holds it there. Full marks need both reasons and the reproducibility argument. Strong answers add what the model cannot see, such as whether a checklist that exists is followed.

**2. Roles and rules.** Product, platform, security and the AI governance council. The catalogue (CAP01) and the acceptable-use policy (CAP02) need two approvers and a security veto (TOM004, TOM006): both decide what data leaves the company and which code runs in its workspaces, so one person's convenience or one vendor relationship must not decide them. The measurement owner sits outside the sponsor's line (TOM003) because the sponsor chose the tool and argued for the budget; a readout they own is not independent. Full marks need the four roles, the two capabilities and both reasons.

**3. Contamination.** Any way the treatment reaches the comparison arm, or the comparison's conditions reach the treated arm. With tasks randomized within engineers: (a) engineers carry habits, prompts and agent-written code into control tasks, making control tasks more like agent tasks, which biases the difference toward zero; (b) agent changes lengthen the shared review queue, so control changes wait longer too, which also biases the lead-time difference toward zero. A third path, people using agents on control tasks against the protocol, has the same direction. Full marks need the definition, two paths and the direction. Strong answers note that the comparison teams' review waits (Lab 20.2's readout) are how the second path is watched.

**4. The irony.** Bainbridge (1983) observed that automating the routine part of a job leaves people the hardest part, taking over when the automation fails, while giving them less practice at the routine work that built the skill to take over. For agents, the routine work is small fixes and debugging; engineers who stop doing it unaided may lose or never build the skill they need when the agent is unavailable or wrong, which is skill atrophy. The pilot's exercise (11 of 15 before, 10 after in the pilot teams; exact McNemar p = 1.000) shows no clear change. Thirteen weeks and fifteen engineers could not show a modest change in either direction, so the result is uninformative, not reassuring. Full marks need the irony, the link and the limit.

## Apply

**5. Team ops.** Practices: P2.1 is met. P2.2 has two items: the newer reports one open high finding, which fails the threshold, and the older is 227 days old against a 180-day limit. So P2.2 is unmet and the team is at **level 1**, with reason "older than 180 days; open_high 1 fails <= 0". The opinion offered for P3.2 would not have counted either. Security: S2.1 (171 days old, limit 365) and S2.2 (share 0.93 against 0.90) are met, so level 2 holds. S3.1's catalogue artifact is 192 days old against a 180-day limit, so the team is at **level 2**, first unmet S3.1, "older than 180 days", even though S3.2 is met. Full marks need both levels, the criteria and the reasons, including that levels are cumulative.

**6. The steady month.** With 34 engineer-months, 8.33 changes per engineer-month and an agent share of 0.8, there are 226.58 agent changes. Gross hours released: 226.58 × (2.04 − 0.55) = 337.6. Failure hours: 226.58 × 0.006 × 16 = 21.75 (the measured +0.6-point difference). An hour is worth $15,000 ÷ 140 = $107.14.

| Realization | Benefit | Cost | Net |
| ---: | ---: | ---: | ---: |
| 0.5 | $15,755.12 | $15,973.38 | −$218.26 |
| 0.75 | $24,797.93 | $15,973.38 | $8,824.55 |

Benefit is (337.6 × realization − 21.75) × $107.14. Cost: model 226.58 × $12.48 = $2,827.67; seats 34 × $40 = $1,360; platform and governance 0.5 FTE × $15,000 = $7,500; junior practice 10 × 4 × $107.14 = $4,285.71; no training. Measure the realization share first: it moves the net by about $9,000 a month between these two values, and no pilot of this design measures it. A way to measure it is to compare planned work completed per engineer-month in holdout and agent-heavy months, or to sample engineers' calendars for what replaced the saved hours, with the privacy limits of Section 20.3. At 0.5 the month is just below break-even, and at 0.75 clearly above it. Strong answers add that the measured +0.6 points understates the configured +2.0-point harm, which would cost about 51 more failure hours, roughly $5,400 a month. Full marks need the three results per row and a credible measurement plan.

**7. A longer pilot.** With the registered paired t-test, D3 at 26 weeks has power 0.827 at a true ratio of 0.85 with task contamination 0.2, and 0.576 with 0.4. D3 needs 23 weeks for 80% power at 0.85 with the default. So a pilot of about half a year would have been enough under the stated assumptions, and not enough if contamination is twice as large. Full marks need the three numbers and the dependence on contamination. Strong answers note that the sign test would need longer, since it has less power for the same pilot (Table 20.5's discussion). Strong answers say how contamination could be estimated during the pilot, for example by comparing control tasks' author hours with the comparison teams' trend.

## Design

**8. Six teams with shared reviewers.** Marking notes; a strong answer covers:

- **Unit.** Teams are too few and share reviewers in pairs, so team-level randomization has little power and heavy contamination. Randomize tasks within engineers (as D3), or randomize reviewer pairs as clusters in a stepped rollout if team-level outcomes matter. Either way, analyse at the randomized unit, with clusters by engineer.
- **The two informal teams.** Their engineers are already exposed; either exclude them from the comparison or include them only in a stepped rollout's last wave, and say how their prior use biases the estimate.
- **Comparison and contamination.** Concurrent comparison work; measure review wait per reviewer pair, agent use in control tasks (workspace logs where the policy allows, anonymous survey otherwise), and the comparison's trend.
- **Power.** Variance components from a baseline quarter; stated assumptions for drift, heterogeneity and contamination, with sensitivity; a minimum detectable effect tied to the ROI's break-even.
- **Outcomes.** Primary: change lead time. Secondary: author and review hours, change fail rate, review wait, satisfaction and psychological safety (anonymous, n ≥ 5), an unassisted skill exercise. No output metrics.
- **Guardrails and owners.** Change fail rate, review load and secrets exposed, each with threshold and window; analysis owner and data steward outside the sponsor's line; assignment list hashed in the registration.

**9. No juniors for two years.** Marking notes; a strong answer covers:

- **Costs left out.** The senior reviewers of 2029 are the juniors of 2027; review is already the scarce resource in an agent rollout (Section 20.3, Chapter 1's queue); Bainbridge's irony and the opening incident's on-call failure; automation bias in reviews, which the reviewing skill guards against (Parasuraman and Manzey); the risk of a single-generation team when people leave.
- **What the saving assumes.** That agents do junior work at junior cost and quality, without measurement; the pilot measured author hours on randomized tasks, not whole roles.
- **Development plan.** Unassisted practice funded and scheduled; pairing with reviewers on agent-written changes; explaining every agent-written change in review; rotating through on-call with a buddy; a quarterly unassisted exercise.
- **Measures and owners.** Exercise pass rates by cohort, time to independent on-call, review findings caught by juniors, and survey measures of confidence and safety; owned by the engineering director as reviewer-capacity owner, measured by the programme's independent measurement owner.

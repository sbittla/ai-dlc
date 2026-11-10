# Chapter 15 — Answers and Marking Notes

Numbers come from the reference solutions of Lab 15.1 (`labs/ch15/L15.1-hardened-pipeline/`) and Lab 15.2 (`labs/ch15/L15.2-canary-kill-switch/`). The ones marked "locked" are checked by each lab's `tests/test_answers.py` or `tests/test_golden.py`.

## Recall

**1. Why did the empty report pass, and what stops it now?**

The March gate checked that the three SARIF files existed and that none held a blocking result. The fallback wrote `{"version": "2.1.0", "runs": []}`, which exists and holds no results, so the gate passed it.

Two checks in Lab 15.1 each stop it:

- The scan stage treats a report with no runs, or one whose tool name is not the expected scanner, as "cannot decide" (exit 2), which fails the pipeline. Candidate P-08 is the incident's report: "blocked at scan (cannot decide)" (locked).
- The pipeline guard's gate diff names the change: GD004 (a `||` fallback after a failing command) and GD005 (a step writing a report itself). Pull request #2604 is blocked with GD004, GD005, PG001, PG002 and PG003 (locked).

The scan stage acts on the release's own evidence: the pipeline runs its own scanners on the release's commit and image, independent of `ci.yml`, so it stops a release with an empty report however the workflow was changed and whoever approved it. The guard acts on the change; it still blocks the change alone (Exercise 5), but it is a review rule, and it holds only because it runs from code the pull request cannot change. Marking: full credit names both and says why the scan stage does not depend on review.

**2. Three ways to break fail closed, and Relay's rule for each.**

- A report that exists but says nothing. Rule: the scan stage requires runs written by the expected tool; otherwise exit 2.
- A skipped job counted as passed. Rule: every condition that lets a later job run names `needs.<gate>.result == 'success'`; required jobs have no `if:` (GD002 flags one).
- A mode or setting nobody set. Rule: an unset or unknown `RELAY_PIPELINE_MODE` deploys nothing.

Accept also: a missing human label (exit 2 in the eval stage), or a guard that cannot read team membership (PG004).

**3. Why the requester's approval does not count.**

The person who asked an agent for a change shares the agent's framing of the problem. In the incident, the engineer had asked for CI to pass, so a green check looked like success. An approval is meant to be an independent reading. Counting the requester would let one person ask for a gate change and approve it, which is the separation of duties Chapter 14 rules out. Pull request #2715 shows the rule: priya.n asked for the change and approved it, and the guard counted two approvals of three.

**4. R4: hold, not rollback.**

From minute 20 to minute 34 both versions burned at 14.4 or more on SLO-API-AVAIL. The canary's bad share stayed within twice the stable version's, so the rule classed those minutes as a shared problem the release probably did not cause: it held its step and paged once, and held minutes did not advance the bake clock. After the incident it resumed and promoted the release at minute 61 (locked). Had the canary been more than twice as bad as the stable version during the incident, it would have been rolled back, and sixty held minutes in a step would also roll it back. All at once, the same burn rule had no stable version to compare with, so it blamed the release and rolled back a healthy version (locked).

## Apply

**5. The incident without PG001.**

With the workflow change in a pull request of its own, the guard reports GD004, GD005, PG002 and PG003, and still blocks (locked). PG002 fails because reviewer-1's single approval is one of the two required. Adding aisha.r's approval satisfies PG002 and the security half of PG003, but PG003 still blocks, because the description has no `Gate change: RLY-n: …` reason (locked).

That rule is worth keeping because it forces the author to say, in writing, that the change weakens a gate and why. The March change was described as making the step "resilient to transient database timeouts". Writing "Gate change: Trivy failures now pass" would have made the problem visible to everyone reading the pull request.

**6. Checking the AI feature every 60 minutes.**

| Check interval | A1 trips at | Suggestions with the feature before the trip | Extra overrides | A0 false trips (of 40) |
| --- | ---: | ---: | ---: | ---: |
| 5 minutes (the policy) | minute 395 | 123 | 20 | 3 |
| 60 minutes | minute 420 | 134 | 21 | 2 |

*All locked. Hourly: drop 9.3 points, z = 2.44.*

Fewer looks give fewer false trips (2 against 3 of 40) at the cost of 25 minutes and one more overridden suggestion in A1. Forty runs are too few to separate 2 from 3 with confidence, so the honest reading is "no clear difference in false trips, a small cost in detection". A good answer either keeps 5 minutes, because the cost of a false trip is low (the feature goes off and a person restores it), or moves to a sequential test designed for repeated looks. Either is acceptable with the reasoning.

**7. One bad minute is enough.**

| Scenario | 3 minutes (policy) | 1 minute |
| --- | --- | --- |
| R1 healthy | promoted at 45 | promoted at 45 |
| R2 3% errors | rolled back at 3 | rolled back at 1 (4 bad answers instead of 7) |
| R3 slow | rolled back at 3 | rolled back at 1 (26 bad answers instead of 55) |
| R4 shared incident | promoted at 61 | **rolled back at 11** |
| R5 quiet hour | rolled back, not judged, at 59 | unchanged |
| R6 one bad minute | promoted at 46 | **rolled back at 7** |

*All locked: both columns, in Lab 15.2's `tests/test_answers.py`.*

R2 and R3 roll back two minutes sooner, a small gain. R4 and R6 are false rollbacks of healthy releases. R6 is the configured one-minute spike. R4 rolls back at minute 11, before its incident: at 5% the canary serves about 60 requests a minute, so a single error is 1.67%, a burn rate of 16.7. Requiring three minutes in a row is what keeps a 60-request minute's noise from deciding. Marking: credit for naming both false rollbacks and the per-minute noise at small canary shares.

## Design

**8. A CI-failure agent that proposes fixes.** Marking notes; look for:

- Identity and permissions: its own registry entry and GitHub App (Chapters 10 and 14), read access to logs and code, the ability to open a pull request, and no `workflows` permission, merge, approve or bypass. No cloud role.
- What it may change: application code and tests only. It may diagnose a pipeline failure, but any change to a pipeline path is a proposal for a person, in a pull request of its own under the guard. The instruction file's rule never to make a check pass by changing the check applies.
- Review: the guard's PG rules, with the person who triggered the agent unable to approve; a gate weakening needs `@relay/security` and a written reason.
- Untrusted input: CI logs contain text from dependencies and pull requests, so the agent's log reading is `untrusted_result` (Chapter 12), and its external effects need approval.
- Test: a drill replaying March's failure. Give the agent the Trivy timeout and an instruction to make CI pass, and check that it hands the task back. If it produces a workflow change, the guard must block it (GD004, GD005) and the scan stage must still refuse an empty report.

**9. A schema change the two versions cannot share.** Marking notes; look for:

- Prefer not to: split it into expand and contract releases (Chapter 9), so each release can run beside its predecessor and the canary applies.
- If it cannot be split, the canary does not apply: ADR-047 refuses a canary to such a release. Use a reviewed plan instead. Run the migration as `relay_migrator` (Chapter 13) in a maintenance window, take a tested backup first, and switch versions blue-green.
- The way back at each step: before the migration, the old version; after it, a tested downgrade (ADR-019) or a restore. Say which steps cannot be undone, and who decides.
- What to compare: during any period with both versions, compare errors on the routes that touch the changed tables, not only the totals. Afterwards, Chapter 16's SLO alerts carry on watching.

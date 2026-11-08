# Chapter 4 — Answers and Marking Notes

Arithmetic in these answers was checked by running code: Wilson intervals with `wilson_interval` from `labs/ch04/L4.2-ambiguity-eval/solution/ambeval/scoring.py` (the Chapter 2 definition), and the business-hours times with a short script over the calendar for November 2026. Impact results are printed by `python -m reqcheck.report ... --impact D1` in Lab 4.1.

## Recall

**1. Problem frame.** Users, outcome, scope, constraints, risks and success measures (Table 4.1). A target alone cannot show improvement: without a baseline measured the same way, "zero unacknowledged P1s" could be no change at all, or a large one. The baseline also tests whether the measure can be counted at all. Relay 4.17.2 cannot count acknowledgements, which is why G1 names a proxy. Full marks need all six elements and the point that the baseline must use the same definition as the target (Chapter 1's definition of a baseline).

**2. Verbatim, five words.** Verbatim, because a paraphrase is a second claim by whoever paraphrased, and only an exact quote can be checked by a machine against the source. At least five words, because a short fragment such as "P1" appears in many places and proves nothing about the requirement. Two ways a verbatim quote can still be wrong (any two):
- The quote is real but misunderstood. ESC-R01 quoted INT-1 exactly and still named "the shift lead", a role Relay does not have.
- The quote comes from text that is not the speaker's position, such as instruction-like text pasted into a transcript (ESC-R06's SMS line).
- The quote is taken out of context: "after thirty minutes" belongs to the second step, not the first.
- The speaker was wrong or out of date, for example about a policy the documentation states differently.

**3. Precision and recall.** Precision: of the statements the detector flagged for a defect, the share that really have it. Recall: of the statements that have the defect, the share it flagged. When the detector flags nothing, precision is 0 divided by 0. Reporting 0% would claim every flag was wrong when there were no flags; reporting 100% would claim perfection on no evidence. Both are undefined, and the report says "n/a". Full marks need the zero-denominator argument, not only the formulas.

**4. NFR categories.** Security, abuse, privacy, accessibility, operability, cost and human-AI interaction. Examples (any two):
- Abuse: flooding a colleague with escalation emails (ESC-N04's cap of 20 per target per hour).
- Privacy: a task title such as a customer's card-data incident leaving Relay in an email (ESC-N07).
- Security: a Member changing a rule through the API when the editor hides the button (ESC-N03's server-side check and HTTP 403).
- Operability: the evaluator stops and nobody notices until a customer complains (ESC-N09).
- Human-AI: an injected ticket steering the triage model to P1 and paging people (ESC-N01).
- Cost: SMS charges with no budget owner (ESC-N10).
- Accessibility: a support lead using a screen reader cannot create a rule (ESC-N08).

## Apply

**5. Business hours over a weekend.** One business hour remains on Friday 20 November 2026 (21:00 to 22:00), so 3 more are needed.
- Every day has business hours: Saturday 21 November 06:00 plus 3 hours, so the step fires at **09:00 on Saturday 21 November**.
- Only Monday to Friday: the next business day is Monday 23 November, so it fires at **09:00 on Monday 23 November**.
- The answers are **48 hours** apart.

The decision: whether a rule's business hours include weekends, and if not, whether each rule can choose its days (warehouses may run seven days; Relay's support team may not). Record it as a new decision (D9), and add a criterion such as: *"Given a P2 rule with business hours 06:00 to 22:00, Monday to Friday, in Europe/Berlin and one step at 4 business hours, when a task's priority is set to P2 at 21:00 local time on Friday 20 November 2026 and it stays unacknowledged, then the step fires at 09:00 local time on Monday 23 November 2026."* Strong answers note that ESC-R07's open question about weekends is listed in the PRD, and that public holidays raise the same question.

**6. Two detectors.**

| Detector | Precision | 95% interval | Recall | 95% interval |
| --- | ---: | --- | ---: | --- |
| A: 9 of 12 flags correct, 9 of 15 found | 75.0% | 46.8% – 91.1% | 60.0% | 35.7% – 80.2% |
| B: 6 of 6 flags correct, 6 of 15 found | 100.0% | 61.0% – 100.0% | 40.0% | 19.8% – 64.3% |

The precision intervals overlap widely, and so do the recall intervals. On 40 statements neither difference is established. A required check blocks merges, so false alarms are its main cost: B's perfect precision is attractive, but it rests on 6 flags. A reasonable answer runs A as a warning (it finds more), and B as a provisional blocking check, with a larger held-out set before B's precision is trusted. Full marks need the intervals, the statement that the differences are within the noise, and a decision that follows the cost of each kind of error. Deduct marks for "B is better because 100% > 75%".

**7. Changing D1 to allow 2-minute delays.** The impact result for D1 lists **2 requirements** (ESC-R04, ESC-R05) and **4 tests** (ESC-AC07, ESC-AC08, ESC-AC09, ESC-AC10). ESC-R04's defaults (10 and 20 minutes) do not change, but its tests should still be re-run. ESC-R05's statement and its Value line change (`step_delay_minutes_range = 2-240`).

Rewritten ESC-AC10: *"Given a P1 rule, when an Admin sets a step's delay to 1 minute, then Relay refuses the change with a message that names the allowed range of 2 to 240 minutes."* A strong answer adds a boundary criterion at exactly 2 minutes.

The best answers also notice what impact analysis cannot list, because no link records it. ESC-N09 requires only 95% of steps to fire within 60 seconds of their due time, which is half of a 2-minute delay, and puts no bound on the other 5%. ESC-N04's flood cap is reached sooner with very short steps. Impact analysis follows recorded links only; a reviewer reads the NFRs against the change.

## Design

**8. Guest access expiry discovery.** Look for:
- **Interviews:** an Admin at a customer that uses contractors (questions about the last time a contractor kept access after leaving; how they found out; what they did); a Guest (the last time access ended unexpectedly); Relay's security lead (abuse and audit); support (tickets about Guest access). Questions about past events, not wishes.
- **Documents:** Relay's roles page (Guests see invited projects only; cannot see the member directory), data-retention page (audit log 400 days on Business, 90 on Team), notifications page, and the baseline `User` model (Guests' `projects`).
- **Abuse cases (any two, each with a requirement and criterion):** an Admin extends their own Guest friend's access silently (audit and notify the Owner); a Guest's access expires mid-task and data is left in their notifications (no task content in expiry emails); a compromised Admin sets every Guest's expiry far in the future (a maximum expiry, and a change notification).
- **NFRs per category:** security (server-side enforcement at the expiry time, within 60 seconds); abuse (as above); privacy (expiry emails carry no task content); accessibility (date picker meets WCAG 2.2 AA); operability (an alert if expiries are not processed for 10 minutes); cost (no new paid service); human-AI (if a model suggests expiry dates, they are suggestions a person confirms).
- **Success measure with a baseline measurable today:** for example, the number of Guests per workspace who are invited to a project but assigned no open task in it, counted at the end of each quarter. Relay 4.17.2 records users, roles, Guests' invited projects and task assignees, so this can be counted now. Measures that need dates Relay does not store (when an invitation was made, when a Guest last signed in) need a named proxy. Target and date set by the product owner.
- Full marks need past-event questions, abuse cases turned into testable NFRs, and a baseline that Relay 4.17.2 can actually count.

**9. Requirements gate in CI.** Look for:
- **Blocking (Relay's `--gate`, Section 4.4 and worked example 2):** checks whose answer is exact given the PRD text: provenance (RQ001–RQ004), criteria present and in Given/When/Then form (RQ020–RQ021), declared-value contradictions (RQ030), NFR coverage (RQ050), traceability (RQ060–RQ065), quotes from flagged source text (RQ071) and the approval record (RQ080). Blocking means a person must fix the PRD or record a decision before merge, never that an agent rewrites the text.
- **Warning only:** the word-list checks, RQ010–RQ012 and RQ040–RQ041. Lab 4.2 measured the matching rules on held-out: the vague-term rule found 3 of 7 ambiguities and the untestable rule 6 of 12. Every flag was right, but on 3 and 6 flags the precision intervals reach down to 44% and 61%, too little evidence to block a merge. Each warning is fixed or answered in the review record.
- **Candidates, not in the gate:** Lab 4.2's word-overlap contradiction rule and its missing-actor rule. The contradiction rule only compares statements within the dataset's labelled sets, so its precision is flattered; the missing-actor rule has one held-out false alarm in 9 flags and was written by the data's authors. Both need a held-out set drawn from real PRDs first.
- **The approval record is not the approval:** RQ080 checks fields anyone can type. The authenticated approval is the product owner's required code-owner review on the pull request that sets `Status: approved` (Chapter 3), with agent identities that cannot approve (Chapter 14).
- **Held-out growth:** new labelled statements come from real PRD reviews, are labelled by two people with disagreements settled, and go into held-out first; held-out is read only to report, and moved into dev only when retired, with the version recorded. Never tune a lexicon on held-out.
- **Model-based checker:** a pinned model ID and prompt version; a cost ceiling per run (`--max-usd`), with "budget_exhausted" recorded; refusals, truncation, API errors and invalid output recorded as outcomes that count as "nothing flagged"; sources passed as untrusted data with instructions separated, and no tools or outbound access (the lethal trifecta, Chapter 3); results reported on held-out, once per prompt version. It may block merges only after held-out precision is shown, with an interval, to be at least as good as the deterministic checks it would join, and re-evaluated whenever the model or prompt changes.
- Full marks need the block/warn split justified with held-out numbers, a leakage-proof process for growing the held-out set, and the model checker's failures recorded rather than hidden.

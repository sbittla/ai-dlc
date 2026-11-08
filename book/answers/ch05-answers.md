# Chapter 5 — Answers and Marking Notes

Arithmetic in these answers was checked by running code: Exercise 5 with `relay.escalation.evaluate` from `labs/ch05/L5.1-spec-first-delivery/solution/relay-repo/` (on 24 November 2026 UTC), and Exercise 6 with `speccheck.plan.waves` and `speccheck.checks.check_tiers` from the same lab's solution.

## Recall

**1. The nine sections.** Goals, Non-goals, Actors, Behavior, Non-functional requirements, Contracts, Data rules, Security constraints, Acceptance criteria (Table 5.3). A security reviewer reads Data rules and Security constraints: together they say what data may go where, which rules must hold whatever the code does, and which executable check tests each. Full marks need all nine and a reason tied to what the security reviewer approves; "because they are about security" alone earns half.

**2. PRD and spec.** The PRD states what users need and why, with sources, decisions and acceptance criteria for the whole feature. The spec states what this code does to meet those needs: its boundary, rules, data and limits, approved before the code. Examples (any one of each):
- In the spec, not the PRD: delays are whole minutes in the field `delay_minutes`; the 10 rejection codes and the order validation checks run in; the 4 evaluation statuses; the data classification of every contract field; what "fires" and "saves" mean at the slice's boundary.
- In the PRD, not the spec (deliberately): business hours for P2 rules (ESC-R07); the flood cap (ESC-N04); email and webhook delivery (ESC-R09); the audit log (ESC-N03); the success measures and their baselines.

**3. Structural and behavioural drift.** Structural: names, types, enum values, IDs or versions differ between spec, contract, code and tests. Behavioural: every name agrees, but the meaning has changed. The drift gate detects structural drift; the test suite detects behavioural drift, but only what its tests assert. Examples from Table 5.11: scenario 05 (`delay_minutes` becomes a float) fails the gate while all 64 tests pass; scenario 07 (`>=` became `>`) fails three tests while the gate passes. Strong answers add scenario 08, which neither catches, and name the human step: reading the criterion-named test against its criterion.

**4. The untrusted-input cap.** Chapter 1: a task in which an agent reads and acts on untrusted content is capped at T2 until defences against prompt injection are tested (Chapter 12). It applies per task because tiers are granted per task type, not per agent or feature (Table 1.6's second rule): the same feature has tasks that read untrusted content and tasks that do not. In the slice, it affects T08, whose agent builds a fixture from the injection ticket TK32. Full marks need the per-task reason and T08 named.

## Apply

**5. Evaluation with three steps (15, 30, 60 minutes; priority set at 02:30 UTC).**

| Case | Status | `fire` (step, due) | `next_due_at` |
| --- | --- | --- | --- |
| 03:05, step 1 already fired, unacknowledged | `active` | step 2, due 03:00 | 03:30 |
| 03:40, evaluator stopped, no step fired | `complete` | step 1 at 02:45, step 2 at 03:00, step 3 at 03:30 | none (`null`) |
| Acknowledged at 02:50 | `acknowledged` | none | none (`null`) |

In the second case every due, unfired step is returned in order, so each fires exactly once even though the evaluator was late (D9), and nothing remains, so the status is `complete`. In the third case acknowledgement cancels the remaining steps whatever time it is (D9); whether step 1 fired before 02:50 does not change the answer. Deduct marks for firing only the latest due step in the second case, or for firing step 2 or 3 after the acknowledgement. Strong answers note that the late steps reach targets late, which is what ESC-N09's operability requirement measures.

**6. Waves and the cap.** Waves: {A}, {B, C}, {D, E}, {F}. The longest chain is 4 tasks (for example A → B → D → F). The checker reports **SP051** (critical, blocking) on E: it reads untrusted input at T3, above the T2 cap. Customer-supplied CSV files are untrusted input, so assign **T2** at most: a sandbox, no merge permission, a person reviewing before anything leaves it. E is also sensitive, which on its own would allow up to T3 with each action approved, but the cap applies first (Figure 1.2: the lower of the two applies). A strong answer considers T1 if the fixtures may contain personal data that should not enter an agent's context at all, and says why.

**7. A repeating last step.** In order:
1. **PRD:** decision D9 says fired steps do not repeat, so the change revisits D9. Lena.k records a new decision (or a revised D9), adds a requirement or amends ESC-R06, and adds a criterion with a new ID (for example ESC-AC32). Sources: the support lead's request, quoted. Run change impact on D9 (Chapter 4).
2. **Spec:** a change proposal; Behavior (B2 rewritten: the last step repeats every 30 minutes until acknowledged; possibly a new status), Acceptance criteria (the new criterion, copied word for word), Data rules if a field is added, and the change log.
3. **Contract:** probably a field such as `Step.repeat_minutes` or a repeat count in `StepDecision`, each with a data rule; the enum of statuses if one is added.
4. **Version: MAJOR**, 1.0.0 → 2.0.0. The change overturns D9's rule that a fired step never fires twice, so the evaluation output for P1 rules that were already accepted changes: later evaluations now return the last step again. By the chapter's definition, a change to the output for accepted input is MAJOR. ESC-AC12 in Lab 5.2's scenario 03 is MINOR by contrast, because it makes previously refused P2 rules acceptable and changes nothing for any accepted rule. Deduct marks for MINOR.
5. **Tests and code:** a test named `test_ESC_AC32_...`, then the code; tasks added to the task list, checked for tiers.

The drift gate blocks a code pull request whose tests have not caught up: **DR001** (the spec says 2.0.0, the tests' modules still say 1.0.0) and **DR030** (the new criterion has no test). A strong answer also notes ESC-N04's flood cap: repeats every 30 minutes add escalation emails, and impact analysis on D7 is needed even though no link records it.

## Design

**8. Guest access expiry spec package.** Look for:
- **Goals and non-goals:** goals tied to the PRD's (Chapter 4, Exercise 8); non-goals such as notification delivery, a user interface, bulk changes, or expiry for Members, each saying where it goes.
- **Actors:** Owner and Admin (set expiry), Guest (affected), the expiry job (Relay code), possibly a model suggesting dates (a suggestion a person confirms).
- **Contract:** an input such as `GuestExpiry {user_id, project_id, expires_on}` (a calendar date, as Chapter 3 taught for due dates), and an output such as `ExpiryResult {user_id, project_id, status, effective_at}` or a rejection with codes.
- **Data rules:** user ID and project ID Internal; the Guest's name and email Confidential and never in outbound documents; the reason an Admin types Confidential.
- **Security constraints (two, each with checks):** only Owners and Admins set or extend expiry, checked server-side (a criterion and a test); an expired Guest cannot view the project within a stated time, checked by a test using `can_view_project`; an extension is audited and the Owner told (deferred if audit is out of the slice).
- **First slice:** criteria whose outcome the slice's code decides, such as refusing an expiry in the past or after a maximum, and whether a Guest can view a project at a given date; display and notification criteria marked partial, with the deferred part named.
- **Security reviewer:** yes. The feature decides who can see customer data, so it is high-risk.
- Full marks need classification for every contract field, constraints with executable checks, and honest partial coverage.

**9. Drift gate for the HTTP boundary.** Look for:
- **Artifacts:** the OpenAPI document (paths, methods, status codes, request and response bodies), the JSON Schema it references (Lab 5.1's contract), the handler code (routes and the documents they return), and tests named after criteria and after operations.
- **Blocking:** an operation or status code in the OpenAPI document with no handler, or a handler with no operation; a request or response body whose schema differs from the slice's contract; version mismatches; a criterion with no test. **Warning:** a test for an operation not in the document; a documented optional field no test exercises.
- **Failure:** exit status 2 when an artifact cannot be read or parsed, which fails the build (fail closed, Chapter 3). The gate is run from a pinned copy owned by the platform team, as a required status check, so a pull request cannot weaken it.
- **A behavioural drift no structural check sees (any one, with its check):** the handler returns HTTP 200 instead of 403 for a Member's rule change, while the documented 403 still exists in the document (a test of ESC-AC21); the handler stops calling `validate_rule` before saving (a test that sends a 4-minute delay through the API); the handler adds the task title to a log line (a test or a log scan for Confidential fields). Full marks need the exit-code policy, where the checker comes from, and a behavioural drift with a concrete test.

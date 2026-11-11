# Chapter 19 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch19/L19.1-maintenance-bot/` (its `relay-repo/` and `solution/mainlab/`) and `labs/ch19/L19.2-safety-security-case/solution/caselab/`. They are locked by Lab 19.1's `tests/test_answers.py` and `tests/test_golden.py` and Lab 19.2's `tests/test_caselab.py`. The incident's counts, the replay and the simulated month are generated and configured (the bot did not run in June); the package `sessionkeel` is fictional.

## Recall

**1. Why every check passed.** The application's tests measured whether `verify` accepts a good token and refuses tampered, expired and wrong-audience ones. They built their own tokens with an audience, so they never exercised the tokens sign-in issues, which carry none. The mirror's quarantine measured only a release's age: it holds new releases for seven days so a malicious one can be found and pulled, and 2.5.0 was neither new nor malicious. The canary measured availability and latency. Relay's availability measure counts a 401 as good, so every refused sign-in looked healthy.

Full marks need all three, each with what it measured and why that missed a changed default. Strong answers add that each check did its job, which is why the fix was a new check (pinned defaults, the round trip) and a new signal (the guard metric), not a stricter version of an old one.

**2. Structured triage.** Triage reads only fields a form or a feed fills in, each checked against an allowlist or a strict pattern: the advisory's package, fixed version and identifier, and the issue form's component and kind. The free text never chooses the task type. A package not in the lock goes to a person (`not_ours`), and anything that matches no rule goes to a person with the reason.

A support case goes straight to a person (`source_needs_a_person`). Its text is written by customers, and by anyone who can pretend to be one, and Relay's support cases carry no structured field the bot could trust. Full marks need the fields-only rule, the default to a person and the reason for support cases.

**3. Controls against a self-edit of the workflow.** In order: the agent step's write list never contains a protected path, so the boundary refuses the edit (`path_not_allowed`); the proposal desk refuses a proposal touching `.github/` (`protected_path`). The `relay-maintenance` GitHub App has no workflows permission, so the code host refuses a push. CODEOWNERS makes `@relay/platform-leads` review any change there, branch protection lets only maintainers merge, and the pipeline guard makes a pipeline change travel alone with two approvals, one from the platform leads. From 4.31.0 the guard covers `maintenance/`, `src/relay/maintenance/` and the bot's tests as well as `.github/`, and treats `maintenance/` as gate configuration, so a change to the bot's policy (a T4 grant included) also needs `@relay/security`.

The first two share one process and one policy file, so they are one failure domain: a bug in the policy loader, or a stolen runner, defeats both. The App, CODEOWNERS with branch protection, and the guard run outside Relay's code. Of those, only the guard needs two people; CODEOWNERS alone is satisfied by one owner's review. Full marks need the list and the failure-domain point, which is what Table 19.4 and defeater D1 record.

**4. Six measures.** Task success, regression rate, rollback rate, intervention frequency, policy violations, and cost per run and per success. Bug reproduction is T1: its output is a draft test a person reads and commits, so no run ends in a merged change, and task success counts merged changes. Its 0 of 5 says the measure does not fit T1 work, not that the bot failed. Every one of its runs is an intervention, by definition. Full marks need the six and the T1 explanation.

## Apply

**5. Clean runs needed.** (a) The Wilson 95% upper bound at zero harms falls to 10% at 35 merged changes and to 5% at 73. (b) With one harm, the bound reaches 5% at 110 merged changes. (c) At two merged changes a month, 110 takes 55 months, about 4.6 years. A task type that rare cannot earn T4 on its record, which is why the table extension stays at T2 for good. Full marks need the three numbers and the conclusion.

**6. A larger replay.** (a) With 9 and 1 discordant updates the exact McNemar p-value is 0.0215 (two-sided, from the binomial with n = 10). (b) Table 19.7's 3 and 0 give p = 0.250. The larger replay is evidence that policy B lets fewer regressions through on those updates; Table 19.7's is no clear difference, so its case rests on mechanisms. (c) Neither replay says how often regressions occur in practice when its regressions were configured or chosen; neither measures review time or the cost of the updates sent to people; and neither shows that the controls would catch a kind of regression not in the set. Full marks need the p-value, the contrast and two limits.

**7. A campaign's budget.** (a) The meter admits an item only if the spend so far plus its $0.025 estimate fits $0.20. After five items $0.15 is spent, and $0.175 fits, so a sixth runs. After six, $0.18 plus $0.025 is $0.205, so it stops: 6 items, $0.18. (b) The run is `awaiting_approval` with reason `budget:usd`, the seventh item is back on the queue untouched, and the escalation is in the audit trail. Only a person other than the requester may approve a raise, with their own proof, through `decide_raise`, which audits a refusal; then `apply_budget_raise` stores it and the campaign resumes. (c) The checkpoint written after item 4: the four items done, the meter at $0.12, and the queue's record that items 1 to 4 are done, so none is repeated. Full marks need 6 and $0.18, the state and the rule for raising, and the checkpoint's contents.

## Design

**8. A case for self-modifying tool contracts.** Marking notes; a strong answer covers:

- **Top claim.** Updating the bot's tool contracts after a runtime change cannot widen what the bot may do without two people's approval, and a wrong update is detected and reverted.
- **Sub-claims, each with evidence and required strength.** The update can only narrow or keep each contract's effect, scope and approval rule (verified: a property test that compares old and new contracts). It cannot add a tool or a write path (verified: the policy refuses a new name; adversarial records like A01 to A07). An independent person reviews every contract change (deployed: CODEOWNERS and branch-protection settings read from the code host). A widened contract is caught before release (verified: a seeded widening fails the check). A rollback restores the previous contracts (deployed: a rollback drill on the running system).
- **Defeaters.** The comparison and the bot share a process; a contract's meaning can change with the runtime's code while its text stays the same; the reviewing person may approve a long diff without reading it (Chapter 9's automation bias); and there is no live measurement of steering for this step.
- **Approvals.** Two people, one from `@relay/security`, neither the bot's owner, approving the case before any task type uses it.
- **What would change.** A new task type marked `self_modification` naming the case; `src/relay/agents/` (or the contract file) leaving the protected list for that task type only; the evidence items added to the case; and the policy still refusing to load if the case is not approved.

Strong answers argue that a deterministic update by a person may be safer than any case for the bot, and say what would make the case worth its cost.

**9. Documentation upkeep and T4.** Marking notes; a strong answer covers:

- **Sample size.** At zero harms A1 needs 73 merged changes; at the simulated month's 11 merged changes a month that is about seven months. One harm raises the total needed from 73 to 110 merged changes, about ten months at that rate. A2 needs interventions below a 10% upper bound, which at zero interventions takes 35 runs, while the simulated month had 3 in 14.
- **A3.** The steered report produced 4 violations, each a refused attempt. Whether a refused attempt should count against the bot is a real question: it measures the input, not the bot. A good answer keeps A3 strict but separates violations caused by marked untrusted input, with a written argument, approved under the same rules as the grant.
- **A4.** The live attack measurement is Chapter 12's open item (owner aisha.r, due 2027-05-31 and overdue). Without it, no task type that reads issues can pass, and the policy loader refuses a grant whose report lacks it, so the plan needs that measurement on the docs step's tools and prompts.
- **A5 and A6.** A kill-switch drill and a rollback drill on the deployed bot, each within 90 days of the report; none has run, because the bot is not deployed.
- **The grant's limits.** Only `docs/` outside ADRs and SLOs; a cap on changed lines; no links to hosts outside Relay's own documentation; the guard as a documentation-build check and a link checker; a weekly sample reviewed by a maintainer; and the kill switch.
- **Withdrawal.** Any harm, any violation not explained by marked input, a missed weekly review, or an intervention rate above the bound.

Answers that argue it should stay at T2 earn full marks if they weigh review time saved against the risk and the evidence cost.

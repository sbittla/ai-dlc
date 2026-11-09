# Chapter 14 — Answers and Marking Notes

Numbers and outcomes in these answers were checked by running code from `labs/ch14/L14.1-agent-identity-kill-switch/solution/agentsec/`: the detection rules with `detect.build_baseline` and `detect.evaluate` on a modified copy of agent-detection-v1, the drills with `drill.run_drill` and `drill.judge` on modified drill plans, and the caller scoping with `report.scoping_run` on a modified registry. All are locked by `labs/ch14/L14.1-agent-identity-kill-switch/tests/test_answers.py`. The data is generated and labelled; the drills run on a simulated clock.

## Recall

**1. What made the incident possible.** Any four, each with its rule:

| Property of the harvester's token (C01) | Rule |
| --- | --- |
| No expiry | IDN001 |
| Shared by two jobs, the harvester and the dataset refresh | IDN002 |
| No recorded owner (its creator had left) | IDN003 |
| Grants beyond need: all six support projects and export, where the harvester needed one project's list | IDN005 |
| Stored in a repository configuration variable instead of being issued at run time (and, not being a secret, never masked) | IDN006 |
| Its actions did not record an agent or a person | IDN008 |
| No drill of its revocation path | IDN009 |

Strong answers add the leak path, which no rule on C01 flags: an agent with a credential that could post publicly (C02, IDN004 and IDN005) and a debug log that printed an encoded secret. Full marks need four correct pairs.

**2. Epochs and DRILL-1.** Every token records the agent's epoch when it is issued. Tripping the kill switch disables the agent and increments its epoch, and `verify` refuses any token whose agent is disabled or whose epoch is old. The check runs against the registry on every verification, so it does not matter where the token was copied to: the attacker's copy is refused on its next use.

The simulated DRILL-1 failed because the gateway did not call `verify` on every request. It cached a token's verification for 300 seconds, so it went on accepting the token until the cached result expired, 210 seconds after the alert. Revocation is only as fast as the slowest consumer that caches a decision. Full marks need both the mechanism and the reason the epoch alone was not enough.

**3. Chains and anchors.** A chain on its own shows that a record was edited (T1: hash mismatch at record 200) or deleted (T2: sequence gap at record 301), because each record carries the previous record's hash. It cannot show that the newest records were cut off, because what remains is still a valid chain (T3 passes). Nor can it show an edit whose every later hash was recomputed, because that is also a valid chain (T4 passes).

An anchor, a copy of the chain's head written to a separate store the writers cannot change, catches both: T3 is "truncated after anchor at seq 524", T4 an "anchor mismatch at seq 203". Strong answers note the remaining gap: records written after the latest anchor can still be cut without trace, so the anchor interval bounds the loss.

**4. Controller or processor.** For the support workspace, Relay is the **controller**: it decides what support does with the tickets people send it. The tickets' requesters are the data subjects. Relay, as controller, must notify the competent supervisory authority within 72 hours of becoming aware of the breach (Article 33), unless the breach is unlikely to result in a risk to people. Its data protection officer advises and is named as the contact point (Article 33(3)(b)), but the controller notifies. It must tell the requesters without undue delay when the risk to them is high (Article 34), which the phishing emails made clear.

For a customer's own workspace, Relay would be a **processor** and would have to tell that customer, the controller, without undue delay; the customer would then decide on the notifications. Customer contracts may set shorter deadlines than the law. Full marks name the role, both articles and who is told; a mark is lost for treating the 72 hours as running from the start of the misuse rather than from awareness.

## Apply

**5. A floor of 5 and a factor of 2 for DR-001.** The harvester's baseline maximum is 0 export starts an hour, so its threshold becomes max(5, 2 × 0) = **5**: more than 5 starts in an hour. The analytics job's baseline maximum is 3, so its threshold becomes max(5, 2 × 3) = **6**.

On the replay, the only DR-001 alert left is the analytics backfill, at **10:15 on 7 December** (the seventh export start in the hour, at 10:12). The first night's misuse started exactly 5 exports, which is not more than 5, so DR-001 no longer fires on it. The misuse is still detected: DR-002 alerts at 19:45 and DR-003 at 20:05, so the first alert is unchanged. But the alert that tripped the kill switch automatically at 19:50, eight minutes before the first download, is gone. DR-003 trips it only at 20:05, after all five exports had been downloaded (the last at 20:04).

Strong answers conclude that raising the floor trades a known false alarm for a slower automatic response, and that a floor should sit below the smallest burst that matters, not above the largest the team has seen.

**6. Short gateway caches.** From `run_drill` with DRILL-1's plan and only the cache changed:

| Gateway cache | Relay refuses after | Meets 60 s? |
| ---: | ---: | --- |
| 30 s | 30 s | Yes |
| 55 s | 20 s | Yes |
| 60 s | 30 s | Yes |

The results depend on when the cache was last filled, not only on its lifetime: the 55-second cache happened to expire soon after the trip, and the 60-second one did not. That is why a single drill cannot prove a cache is safe. The guarantee comes from the worst case, using the chapter's one definition: time to revoke runs from the alert to the first refusal after which nothing is accepted. A cached result filled just before the trip (4 seconds after the alert) lasts c seconds more, and the first refusal comes at the next request, at most 2 seconds later. So time to revoke is at most 4 + c + 2, and 4 + c + 2 ≤ 60 gives **c ≤ 54 seconds**. (A requirement written as "nothing accepted after 60 s" would allow c < 56; the book uses the first form because it is what a drill observes.)

Full marks need the table and the worst-case bound. Strong answers add that the cloud side's assumed 29 seconds (51 with a cloud role) also counts against the same 60 seconds, and that the simplest safe design is no cache for revocable tokens.

**7. A 100-row budget.** With the coding session's budget lowered to 100 rows an hour, the 97 requests give **51 answered**, **100 rows** returned, and refusals of **39 out of scope** and **7 over budget**. The budget first refuses at request **Q91**, 900 seconds into the replay (15:15:00), after the session has spent its 100 rows on its own workspace's tasks.

The out-of-scope count is unchanged, because scope is checked before the budget. Strong answers observe that a smaller budget stops a harvest sooner but also cuts a legitimate session short, and that the right budget comes from the session's real needs, measured in the trail.

## Design

**8. A reply-drafting agent.** Marking notes; full marks need each element with a reason.

- **Registry entry:** its own agent id, kind `ecs-task` (or `ci-job` if it runs in CI), owner tomas.b, its own role and exact workload subject, `max_ttl_seconds` 900.
- **Delegation:** `required`, with the support engineers as delegators. The engineer's own short-lived sign-in token is the subject token, so every draft names the engineer it was written for and the agent cannot name anyone else. Not `owner`: the drafts act for whoever opened the ticket.
- **Scopes:** read one ticket and its thread, and write a draft reply that a person must send. No export, no list of all tickets, no send. A separate send scope, held by people only, keeps the decision with the engineer.
- **Tool limits:** tickets in the support workspace only; a row or ticket budget per hour per engineer, set from measured use.
- **Detection:** DR-002 and DR-003 apply as they are. Add a rule for drafts written without a ticket being opened by its delegator, and for any attempt to use a send scope.
- **Kill switch:** the `ecs-task` path (quarantine the role, stop its tasks), drilled within 90 days.
- **DPIA flows:** ticket text into the prompt, minus requester fields where the draft does not need them; the draft itself, stored with the ticket; traces, redacted, 30 days. The model provider's terms recorded.
- **AI Act, first pass:** apply Lab 14.2's questions. It is an AI system, not a prohibited practice and not in an Annex III area. It generates text, so question 4 gives transparency under Article 50(2), as for F3, unless counsel finds that the exception for systems performing an assistive function for standard editing applies. With a person reviewing every draft, Article 50(1) does not apply, because the agent does not interact with customers directly.

If replies were sent without review, the agent would interact directly with customers, so Article 50(1) applies as well as Article 50(2). Customers must be told they are talking to an AI system, and the risk assessment, detection and DPIA change with it. Strong answers also note that the lethal trifecta now has its third leg, a way to communicate out, and add an output check before any send.

**9. A red-team program.** Marking notes; look for a program, not an event.

- **Cadence:** adversarial cases in CI on every change to prompts, tools or agent configuration; seeded detection cases with every rule change; a quarterly purple-team session; a bug bounty open all year.
- **Starting cases:** Chapter 12's adversarial evaluation set, Lab 14.1's D01–D04, and a case for every incident (the leaked token, the posted log).
- **Bug bounty scope:** cross-tenant data access through agents or tools, tool or credential misuse outside a task, secrets in agent output or logs. Out of scope: wrong or rude text with no security effect, jailbreaks that change only text. A dedicated tenant with synthetic data.
- **ATLAS mapping:** each case mapped to a tactic and technique, with the ATLAS version recorded, and a list of tactics with no case.
- **Metrics with denominators:** attack success rate on the versioned set (n cases), time to detect per case and incident, time to revoke per drill and path, detection coverage as "k of n seeded malicious cases, misses named".
- **From finding to test:** every confirmed finding gets an owner and a target date, and becomes a seeded case or adversarial test that fails before the fix and passes after it.

Strong answers say what a quarter's report would show and which decision it would change, for example the floor in Exercise 5 or the cache in Exercise 6.

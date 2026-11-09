# Chapter 16 — Answers and Marking Notes

Numbers come from the reference solutions of Lab 16.1 (`python -m slolab.report …`) and Lab 16.2 (`python -m gameday.report …`). Exercises 5 and 6 are locked by `labs/ch16/L16.1-otel-redaction-slo/tests/test_answers.py`, and Exercise 7 by `labs/ch16/L16.2-game-day-postmortem/tests/test_answers.py`.

## Recall

**1. Why a 401 is a good event.** The SLI asks whether the server did what it promised. Refusing an unknown or stolen token is the promised behaviour, so a 401 is good for availability. If 401s counted as bad, a burst of guessed tokens would burn the availability budget and page the platform on-call for what is a security event. Worse, an attacker could spend the budget on purpose and trigger the budget policy's release freeze, a denial of service on Relay's delivery. The surge belongs to SD-001, which pages the security on-call.

*Marking:* full marks need both the user-side definition of good and the consequence for paging or the budget policy. Credit an answer that notes the 2 February failures were on the web sign-in path, outside `/v1`, and so would have touched SLO-API-AVAIL only through any API tokens the attacker tried.

**2. Long and short windows.** The long window makes an alert significant: a row fires only after a meaningful share of the budget is already spent (2% for the 1-hour row). The short window, one twelfth as long, makes it stop soon after the problem stops, because it empties quickly. In Table 16.5, the single 1-hour window reset 56 minutes after E1 ended and 58 after E3; the multi-window policy reset after 29 and 4. E1's 29 minutes is the 6-hour row's 30-minute short window emptying.

**3. Verdicts.** Supported, unsupported, contradicted. At 15:18, v0's H0 cited only that the deploy existed and that it came before the slow requests: timing, no mechanism, so it was unsupported. Citing the sign-ins' share of database time as its mechanism would not have helped: a mechanism citation must name the deploy's own component, the notifications, which took 0.3% of database time. At 15:41 the checker's counter-query found the effect still elevated after the deploy was undone at 15:31, slow requests at 206 times their baseline, so it was contradicted. An unsupported hypothesis may be true; it may not justify an action.

**4. What telemetry never records.** Any four of: prompt and response content (`gen_ai.input.messages`, `gen_ai.output.messages` and the other content keys), tool arguments, request headers, query strings, request bodies, user IDs or the person an agent acts for, raw paths, client IP addresses, credentials. Instead: a prompt by version and SHA-256 (`relay.prompt.version`, `relay.prompt.sha256`); a client by its /24 or /48 network prefix (`relay.client.network`); a credential by a keyed HMAC fingerprint, 16 hex characters (`relay.credential.fingerprint`).

## Apply

**5. Latency thresholds and detection times.** For a 99% objective the budget share is 1%, so the rows need 14.4 × 1% = 14.4%, 6 × 1% = 6% and 1 × 1% = 1% bad in their long windows. After a step to 90% slow, the 1-hour row's long window reaches 14.4% after 0.144 × 60 / 0.9 = 9.6 minutes and its 5-minute window after 0.8, so it fires at 9.6 minutes. The 6-hour row needs 0.06 × 360 / 0.9 = 24.0 minutes, and the 3-day ticket row 48.0 minutes. The lab's page came 10 minutes after the step, because evaluation runs at the end of whole minutes and the generated traffic is noisy.

**6. A 60-minute static rule.** It pages 20 times, 16 of them for nothing, and pages for all four events, including E4, which spent 1.3% of the budget and is not significant. It is better than the 5-minute rule's 732 pages but still not a good alert: four in five pages are false, it pages for a slow burn that deserves a ticket, and it still says nothing about how much budget an event spends.

**7. The rollback through the gate.** The assistant's request is refused as `unsupported_hypothesis`, and the refusal is audited under the assistant's identity. As of 15:22 the citation check marks H0 unsupported: it cites the deploy and its timing, but no mechanism. An agent may not act on a hypothesis that is not supported, whatever the deploy record says.

When the on-call engineer (taken as priya.n for the exercise) requests the same rollback citing H0, the gate refuses it as `override_reason_required` until the engineer writes a reason. With the reason, the gate records an `override` and a `requested` entry. The rollback's precondition holds (the 15:00 deploy is within two hours). The engineer and sam.o each approve with a fresh proof bound to this request; their roles cover platform on-call and tech lead, so the status becomes `approved`. A proof sam.o got at 15:16 is more than 300 seconds old at 15:22, so that decision is refused as `stale_proof` and audited.

The point is that the gate cannot stop two determined people, but it makes them write down that they are acting against an unsupported hypothesis. On 2 February that sentence would have said "the deploy came first", which is the evidence the citation check had already called timing alone.

*Marking:* full marks need the assistant's refusal and its reason, the override and the two-person approval, and the stale-proof refusal.

## Design

**8. SLOs for the spec-to-PR helper.** Look for SLIs a requester would recognise: share of runs that end `finished` with a pull request whose checks pass; share of runs that end without `unknown_outcome`; time from request to draft pull request. Good answers note the low volume (tens of runs a week), so the objectives open tickets with long windows (7 days) and a minimum event count, never pages, like Relay's AI objectives. Budget stops and unknown outcomes already raise AL-004 and AL-005 per run. The budget policy should stop prompt, model or routing changes for the helper when its budget is exhausted, until Chapter 10's comparison is rerun on new tasks. Deduct marks for an SLI built on the model's own confidence, or for pages on a handful of runs.

**9. A second game day.** Look for two faults with stated sizes, start times and stop conditions, one reliability and one security. One fault must put instructions in telemetry the assistant reads (a ticket title, an export name, a user agent), with the expected outcome: the assistant may propose, the gate refuses, the proposal is audited, and a case enters the adversarial evaluation set. Expected alerts and their expected times should follow from the rules (for example DR-002 at the first five-minute boundary). Measures are time to detect, to acknowledge and to mitigate per fault. Strong answers fix the first game day's finding by grouping DR-002 and DR-001 for one identity into one page, register the game-day identities for the day only, and freeze deploys.

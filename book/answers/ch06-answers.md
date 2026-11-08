# Chapter 6 — Answers and Marking Notes

Arithmetic in these answers was checked by running code: availability and minutes with `structure.path_availability` and `structure.unavailable_minutes`, and rescoring with `weighted_score` and `weight_to_flip`, all from `labs/ch06/L6.1-architecture-options-adr/solution/archscore/`. Exercise 7's timeline was produced by running Relay 4.19.0's `TriageQueue` and `Worker` (`labs/ch06/L6.1-architecture-options-adr/relay-repo/src/relay/worker/`) with a scripted triage client that always fails at once, and a clock advanced one second per pass. All three are locked by `labs/ch06/L6.1-architecture-options-adr/tests/test_answers.py`.

## Recall

**1. Architecture drivers.** A requirement or constraint is a driver when the choice of structure changes how well, or at what cost, the system can meet it: a quality attribute with a threshold, or a fact about the team, release process or platform. Either of Chapter 4's two non-drivers earns the mark:
- ESC-N08 (WCAG 2.2 AA and keyboard-only use of the rule editor) is a property of the interface, the same in every option.
- ESC-N02 (calibrated confidence) is decided by the triage model and its evaluation (Chapter 7), not by how Relay is deployed.

Full marks need the reason, not only the ID. Strong answers note that the catalogue keeps them at weight 0, so a reviewer can see they were considered.

**2. Tie rule and must drivers.** On a tie the evidence does not separate the options, so the rule prefers the one that costs less to run and change: fewer deployable units means fewer pipelines, contracts and things to page someone about. Chapters 2 and 4 made the same choice on ties, and the rule writes it down so nobody has to argue it each time.

In Relay's catalogue a must driver is one of the PRD's prohibitions, on who decides priority, who changes rules, where data goes and what is paid for (ESC-N01, ESC-N03, ESC-N05, ESC-N07, ESC-N10), plus CON-4, no request waiting for the model. Thresholds marked for review after the pilot (D7, D8) are weighted instead. Points elsewhere cannot compensate for breaking a must, because the result would be a system that violates a requirement someone signed. A weighted sum alone would let a high total hide that.

**3. Idempotency key, lease and 422.**
- The idempotency key protects against a client's retry creating a second job when the first request succeeded but its response was lost.
- The lease protects against a worker that died, or stalled, holding a job forever; when it expires, another worker claims the job. Once a second worker holds the job, the owner check in `complete` and `fail` stops the first worker, if it wakes, from overwriting the second one's work. A job whose lease expires after its last attempt goes to a person rather than being claimed again.
- A reused key with a different body means the client has a bug: it is calling two different requests the same thing. Creating a new job, or returning the old one, would each hide the bug and pick one meaning silently. 422 makes the client fix it. Keys are scoped to a workspace so one customer's key cannot collide with another's.

**4. What static rules cannot see.** Any two, each with a control:
- A dynamic import (`importlib.import_module("relay.worker.queue")`, V08). Control: code review, and a review checklist item for dynamic imports; a runtime check is possible but costly.
- A network call through a subprocess (`curl`, V09) or any other non-import mechanism. Control: egress rules on the production environment (Chapter 11), so the call fails wherever it comes from.
- Runtime properties, such as ESC-N09's 95% of steps within 60 seconds. Control: a runtime fitness function in observability (Chapter 16) and load tests (Chapter 17).
- Drift in data ownership through SQL (a module reading another module's table by name). Control: separate database roles per module, or a rule that scans SQL strings, with its own blind spots.

## Apply

**5. Moving notification out.**

| Path | Components | Availability at 99.9% each | Unavailable minutes per 30 days |
| --- | ---: | ---: | ---: |
| Option A | 2 | 99.80% | 86.4 |
| Notification extracted | 4 | 99.60% | 172.5 |
| Option B | 7 | 99.30% | 301.5 |

Extracting notification doubles the minutes in which steps cannot fire, from 86.4 to 172.5 per 30 days, under Equation 6.1's independence assumption. For Option B's seven components to match Option A's path (0.998001), each would need 0.998001^(1/7), about **99.9714%**: roughly 12.3 minutes of unavailability per 30 days per component instead of 43.2.

Strong answers say what that costs (redundancy for every service, the broker and four databases), and question the assumptions: shared infrastructure makes failures correlated, while a broker can absorb short outages, so the series model is a first estimate in both directions.

**6. Rescoring Option B.** With ESC-N07 and ESC-N03 each raised from 1 to 2 (weight 3 each), Option B gains 3 + 3 = 6 points: **58 of 93**, against Option A's 75. The gap falls from 23 to **17**.

No single weight from 0 to 5 flips the ranking. Option B leads only on CON-3 and CON-6, by one point each, so either weight would have to rise by 18. With CON-3 and CON-6 both at 5, the totals are Option A **91** and Option B **82**, of 117: Option A still leads by 9. Option C stays second throughout: with CON-3 and CON-6 at 5 it reaches **88**, still behind Option A's 91.

The point to make: the ranking is robust to the security reviewer's objections and to weights, so the decision rests on CON-1, CON-2, ESC-N04 and ESC-N01, where the options differ by two points. That is where a review should spend its time.

**7. Retries and attempts.**

| Time | Request or event | Result |
| --- | --- | --- |
| 10:00:00 | POST, key `ticket-0001` | 202, job 1 created (the client never sees it) |
| 10:00:05 | Same key, same body | 202, the same job 1, header `Idempotent-Replayed: true` |
| 10:00:06 | Same key, different text | 422; no job created |
| 10:00:10 | Attempt 1: model unavailable | Back to the queue, available after 10 s |
| 10:00:20 | Attempt 2: model unavailable | Back to the queue, available after 20 s |
| 10:00:40 | Attempt 3: model unavailable | Attempts used (3): **needs_human** |

One job exists throughout. A person sees the ticket untriaged at 10:00:40. Full marks need all three status codes, one job, and the 10 s and 20 s backoffs. Strong answers note that the timeline would stretch by the latency of each failed call, capped by the 10-second timeout, if calls failed slowly rather than at once.

## Design

**8. A live triage adapter.** Marking notes; look for:
- **ADR.** Options: a provider SDK pinned as a dependency; the standard library's `urllib` with hand-written retries; a sidecar or gateway owned by the platform. Drivers: CON-4 (still asynchronous), ESC-N01 (output remains a suggestion), ESC-N07 and the provider's data-handling terms (Chapter 2), cost (ESC-N10 is about notifications; triage spend needs its own ceiling), CON-1. Every rejected option has a testable reason and a revisit condition; the decider is a named person.
- **Fitness rules.** AR4 and FF004 must allow network modules in exactly one new module, for example `relay.worker.live`, and nowhere else in the worker. FF005 needs the SDK in `pyproject.toml` and an accepted ADR with a `Dependency:` line. The change to the rules is itself reviewed by the rules' code owners.
- **Threat model at TB2.** Credentials (where the API key lives, who can read it; Chapter 14); ticket text leaving Relay (provider terms, redaction); injected tickets (suggestion only, enum-only output); provider outage (queue, timeout, person's queue); cost runaway (per-call token limits and a daily ceiling).
- **Failures as outcomes.** API errors, refusals and truncation are recorded on the job (`last_error`), never raised as crashes or turned into guessed labels, as in Lab 2.1's live mode. A cost ceiling is stated in the README and enforced by a counter that stops calls when reached.
- Weak answers add the SDK without an ADR or loosen AR4 for the whole worker.

**9. Chapter 5's module and a runtime fitness function.** Look for:
- `relay.escalation` as a domain module: it may import `relay.models`, `relay.store`, `relay.roles`; it must not import `relay.service` or `relay.worker`. The worker imports it to run evaluation passes; the service imports it to expose rule routes. Notification is reached through the worker, so escalation code makes no network calls.
- Rules: add `relay.escalation` to FF001's and AR1's domain lists; a new rule that only `relay.worker` and `relay.service` may import `relay.escalation`'s internals through its public interface; FF004 already covers network calls. A seeded case for each new rule.
- Runtime fitness function for ESC-N09: for every step fired in the week, the delay between due time and fire time; population all steps in pilot workspaces; period one calendar week, UTC; pass when at least 95% are within 60 seconds. It runs in production observability (Chapter 16), with a weekly report and an alert, not in CI. A failure opens an incident with the platform on-call and blocks further rule-engine releases until reviewed.
- Strong answers also cover the 5-minute stall alert (a heartbeat, as the triage worker has) and note that the 60-second and 95% values come from decision D8 and are reviewed after the pilot's first month.

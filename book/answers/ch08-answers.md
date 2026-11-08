# Chapter 8 — Answers and Marking Notes

Arithmetic in Apply answers was checked by running Lab 8.1's `relay.escalation.hours.add_business_minutes` and `testfirst.oracle.check_oracles`, and Lab 8.2's `mutate.score.Score` and `gate`, on the stated inputs. `labs/ch08/L8.1-test-first-agent/tests/test_answers.py` and `labs/ch08/L8.2-mutation-property-repair/tests/test_answers.py` lock the results.

## Recall

**1. Oracles.** A test oracle is whatever decides whether an output is right: a value written in the test, a rule the output must satisfy, or a second implementation. Independent oracles from the chapter (any three): a hand-worked example from the spec; a law the code does not read (the EU, US, Australian and New Zealand daylight-saving rules against Relay's table); a standard-library recomputation (`hmac` for the signature); a slow, obvious reference (counting business minutes one at a time); an invariant the spec states (a step never fires early). An agent's expected values for code it wrote in the same session share its reading of the requirement, so its errors in code and test are correlated and cancel when the test runs. It also tends to run the code and record the output, which turns a bug into an expected value. Full marks need the correlation argument, not only "the agent might be wrong".

**2. Failing for the right reason.** A new test fails because the behaviour it checks does not exist yet; in the labs, a `NotImplementedError` raised inside the code under test. Wrong reasons (any one): a typo or wrong fixture name (`NameError`), an import of a module that does not exist, a wrong argument count (`TypeError`) in the test itself. Passing before the code exists (any one): it tests a helper the starter already provides (Lab 8.1's zone-table tests, which is why they live in their own file), or it asserts nothing that the missing code decides, such as `pytest.raises(Exception)` when the stub raises `NotImplementedError`.

**3. Surviving and equivalent mutants.** A surviving mutant is one every test passes on; it may reveal a missing test. An equivalent mutant behaves like the original for every input the spec allows, so no test can kill it. Every equivalent mutant survives, but most survivors are not equivalent. Relay prints both scores because equivalence is a judgement: printing the score with no claims makes an over-generous list visible, as `delivery.py`'s 87.5% raw score shows. Deduct for answers that treat "survived" and "equivalent" as synonyms.

**4. Flaky tests.** Causes and controls (any two): time, prevented by passing the time as an argument and never reading a clock; randomness, prevented by fixed seeds in every property and fuzz test; the network, prevented by having no test reach it; test order and shared state, prevented by each test building its own in-memory store. Tests named after criteria or security constraints are never quarantined because quarantine would silently remove the evidence for a requirement; such a test must be fixed, or the requirement's evidence restored, before merges continue.

## Apply

**5. Business hours.** Worked from B3, D10 and D11:
- (a) Friday 15:30 to 17:00 Tokyo gives 90 minutes; 150 remain. Saturday and Sunday are not listed. Monday 30 November opens at 08:00; 150 minutes later is **10:30 Tokyo, 01:30 UTC** on Monday 30 November.
- (b) With Saturday listed, the 150 minutes run from 08:00 Saturday: **10:30 Tokyo, 01:30 UTC** on Saturday 28 November.
- (c) Friday 26 March 2027, 20:30 to 22:00 Berlin gives 90 minutes (Berlin is UTC+1, so the start is 19:30 UTC). Monday 29 March opens at 06:00 Berlin, now UTC+2 after the change on 28 March; 150 minutes later is **08:30 Berlin, 06:30 UTC**. An answer using UTC+1 for Monday gives 07:30 UTC, which is the H4 bug.
- (d) Monday 15:00 Tokyo plus 120 minutes reaches 17:00 exactly; B3 says a delay ending at the close is due at the close: **17:00 Tokyo, 08:00 UTC** on Monday 30 November, not 10:00 on Tuesday (the H2 bug).

**6. Mutation score.** With the claims: 112 / (140 − 6) = 112 / 134 = **83.6%**. Without: 112 / 140 = **80.0%**. To reach 90% with the claims: ⌈0.9 × 134⌉ = 121 kills, so **9 more**. Recording the 8 uncovered mutants as equivalent too gives 112 / (140 − 14) = 112 / 126 = **88.9%**, still below 90%. The proposal is wrong in principle as well: a mutant on a line no test executes has not been shown to behave like the original; the line is simply untested, which is the weakest test of all. The policy counts uncovered mutants as surviving for that reason.

**7. Oracle check.** The check reports **OI01 on the first test** (the expected value is computed by `add_business_minutes`, the code under test) and **OI03 on the third** (it asserts only that a result exists). The second is allowed: it recomputes the HMAC with `hmac.new` from the body, an independent function, which is a legitimate oracle. The fourth compares with a literal, so the check passes it. Questions for review (good answers raise at least one): where did the fourth test's literal come from, a hand calculation or a run of the code? And in the second, is `body` the bytes actually sent, or bytes the test built itself?

## Design

**8. Test strategy for rule deletion and ESC-AC25.** Marking notes. A strong answer includes:
- Risks: a P1 rule deleted silently (G1), notices sent late or to the wrong people, a deletion by a Member, an unaudited deletion, a notice that leaks task content.
- Levels and oracles: unit tests of who receives notices (the Owner and every Admin, from the fixture, written by hand); engine tests that the outbox holds one notice per recipient within the pass, with the timing oracle "5 minutes" from D8; API tests for `DELETE`; an audit test with before and after.
- Refusal matrix rows for the new route: no token (401), Member and Guest (403), unknown rule and another project's rule (404), and the 405 row that exists today replaced.
- A property: for any sequence of create, change and delete operations, every P1 rule change produces exactly one notice per Owner and Admin, and none for other priorities.
- Mutation target: the new code joins the policy's critical modules at 90%.
- Process: the tests are written or approved by a person before code, the agent works at T2, and aisha.r reviews the notice content against ESC-N07.

**9. CI gates for agent-written tests.** Marking notes. Per pull request: the suite, the oracle check (blocking on OI01 and OI02), and the test-first grader where a task names its test files. Nightly, and on pull requests that change critical modules: mutation testing with `--gate`, opening an issue on failure. Approved tests protected by code owners on security-relevant test files, by the commit-order rule, and by a check that the code commit does not modify the test commit's files. Gate tools run from a pinned copy outside the pull request (Chapter 5's lesson). Equivalence claims and quarantines need a named reviewer and an expiry. A remaining weakness (any one, with its human step): an agent replaces a hand-worked literal with a value copied from a run, which no static check sees, so the reviewer reads each changed expected value against the spec; or an agent adds tests that kill mutants without checking requirements, so review reads tests against criteria, not against the score.

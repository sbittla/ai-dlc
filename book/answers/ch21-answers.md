# Chapter 21 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch21/capstone-kit/solution/capstone/`. They are locked by the kit's `tests/test_answers.py` and `tests/test_golden.py`. The fixture teams and their systems are fictional; the Relay sample pack uses Relay 4.31.0's real artefacts and other labs' reports, which rest on simulated models and generated records where those labs say so.

## Recall

**1. Labels.** Verified (a check ran on the system's own artefacts and passed), modelled (the result comes from a simulation, a simulated clock or a configured model), deployed (a record shows the control running where it is claimed to run) and open (no evidence yet, with an owner and a date). Lab 10.1's comparison must be labelled **modelled**: its model's behaviour is configured in `data/simulator.json`, and the report says "Simulated". The kit refuses a report that says simulated but is labelled verified or deployed (EV004). Full marks need the four labels and the reason. Strong answers add that modelled evidence can still back a criterion, but the label travels with it, so the panel weighs it accordingly.

**2. Recomputing the verdict.** A claimed verdict is the team's opinion of its own evidence; the coverage gate's verdict follows from the matrix's cells and the controls' failure domains, so the kit computes it and compares. Otherwise a team could claim PASS over a matrix that fails, which is a check that cannot fail. The fixture `a-fail-overclaim` claims PASS and coverage 2 for class K2, but its two controls share the `notifier` failure domain. The kit recomputes coverage 1, reports two EV004 findings for the false claims and an EV011 for the shortfall. Full marks need the reason and the fixture.

**3. Commit, freeze, reveal.** At the red-team exchange the panel publishes the SHA-256 of a secret seed. At the readiness review the team freezes its contribution statements, and the review records their hash. At the defense the panel reveals the seed, and the kit checks it against the commitment (DF004) and the statements against the freeze (DF001). If the panel committed after the freeze, it could search for a seed that draws a chosen part for a chosen member, because the frozen statements are then known. If the seed were a date string, a team could guess it from the published hash before the defense and rehearse its draws. The kit checks hashes, not dates, so the instructor confirms the order from the records. Full marks need the three steps, both attacks and the 128-bit randomness requirement.

**4. Gates.** Security, reproducibility, explain your work, AI-use disclosure, and cloud and data hygiene. They are not weighted so that a high score cannot hide a failure that matters more than any score: an open high finding, a system nobody can rebuild, or a member who cannot explain the work. The explain-your-work gate is graded per person: a member who fails it fails, and the team keeps its level. Full marks need the five gates, the reason and the per-person rule.

## Apply

**5. Rubric arithmetic.** (a) Correctness, verification, operations and agent reliability rest on sound evidence and keep their scores: 80, 85, 70 and 88. Security rests on the red-team log, which is missing, so it is capped at 59. Traceability rests on the safety case, which has a blocking finding, so it is capped at 74. The total is 0.20 × 80 + 0.20 × 59 + 0.20 × 85 + 0.15 × 70 + 0.10 × 88 + 0.15 × 74 = 16.0 + 11.8 + 17.0 + 10.5 + 8.8 + 11.1 = **75.2**, Acceptable. (b) The security gate cannot pass without a red-team exchange: nobody can say no critical or high finding is open. A failed gate makes the level **Fail**, whatever the total. (c) With the log added and every finding closed, and the safety case fixed, the same scores count in full: 16.0 + 18.0 + 17.0 + 10.5 + 8.8 + 13.8 = **84.1**, Acceptable. Full marks need the two caps, both totals and the gate's effect. Strong answers note that 75.2 sits just above the Acceptable line only because operations and reliability carry it, and that the panel's 92 for traceability was never countable.

**6. Coverage.** A {d1}, C {d3} and D {d2, d4} are pairwise disjoint, so coverage is **3**; B shares d1 with A and d2 with D. If d1 fails, A and B drop out and C, D remain: 2. If d2 fails, B and D drop out and A, C remain: 2. If d3 fails, C drops out and A, D remain: 2. If d4 fails, D drops out; the best disjoint pair is A, C (or B, C): 2. Every single failure leaves 2, so the class meets its minimum under any single domain failure. Full marks need 3, the four values and the conclusion. Strong answers say that B adds nothing to coverage here, because every set containing it is no larger than one without it.

**7. Red-team triage.** F1 is closed: fixed, with a pull request and a re-test that blocked it. F2 is **RT005**: a formal block needs a reviewer outside the defending team, and its reviewer is a member. F3 is medium, so it may stay open; the kit reports nothing. F4 is **RT007** (fixed without a re-test that blocked it, because the re-test says the attack still reached its goal) and **RT005** (a high finding not closed). All four findings are valid, so the attacking team earns **4** credits. (Had F4 been marked "not reproduced" instead, it would close only with a confirmation from outside the team.) The defending team earns **2**: one for F1's re-tested fix and one for F1's detection. Full marks need the three findings with codes and both credits.

## Design

**8. Closing the Relay sample pack.** Marking notes; a strong answer covers each blocking finding:

- **R11, coverage for 4.29.0.** Run Chapter 12's matrix on 4.31.0's code. The book records no owner for a re-run, so the answer must propose one. Keep the deployment records' "generated" label: inside the snapshot nothing better exists.
- **R19, readiness "not ready" for 4.30.0.** Repeat the review on 4.31.0 (sam.o and aisha.r reviewed the first). Rows 4, 7, 8, 9 and 14 need Chapter 18's open items: the dead-job alert, the cloud sandbox runner, the delegation grant and the helper's spend quota. The first three have recorded dates (16 April to 31 May 2027) that have passed with no completion recorded; the spend quota has no date, only a condition: before the helper leaves its pilot.
- **Missing spec package.** Write the helper's spec from ADR-027 and Chapter 10's task definitions, with acceptance criteria for the helper itself, approved by the product owner (lena.k in the book).
- **Missing red-team log.** Another team's exchange under signed rules of engagement; no attack text in the log.
- **Missing signature records.** Real signing in the release workflow, replacing the stand-in digests; this cannot be done inside the teaching snapshot, and the answer should say so.
- **Missing safety case.** A case for the helper in Lab 19.2's form, with defeaters stated.
- **Missing disclosure and statements.** An AI-use disclosure, and contribution statements naming authors, which Relay's records do not hold.

Dates are the student's to propose, but owners must be those the book records where it records them. Full marks need every finding addressed and an honest split between what can and cannot be closed in the snapshot.

**9. A live attack-success-rate measurement for Harbor.** Marking notes; a strong answer covers:

- **Scope and ethics.** Only the team's own Harbor sandbox, inside the rules of engagement, with the ethics agreement cited in the record.
- **The attack set.** Written by the team or supplied by the course, versioned, and kept in the course repository; the evidence pack holds its version and hash, never its text.
- **Configurations.** The model, prompts and tool set pinned and named; before and after hardening as paired configurations on the same cases.
- **Judging a goal.** By what happened in the sandbox (a payment record, an outbound request at the egress proxy, a memory write), not by a model's opinion of a transcript.
- **Runs and size.** Several runs per case for nondeterminism; Wilson intervals on the per-attempt rate; paired comparison of before and after with McNemar's test on cases (Chapter 7); power stated for the difference the team claims.
- **What it adds.** The coverage gate shows that each class has independent controls that stop its known variants. The measurement shows how often the whole system, model included, is beaten by variants the controls were not built around. It can find a class the catalogue lacks.

Full marks need the ethics constraint, the out-of-pack attack set, the judging method and the statistics.

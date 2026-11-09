# Chapter 9 — Answers and Marking Notes

Arithmetic in the Apply answers was checked by running Lab 9.1's `prkit.prcheck.check_pr` and `sizes`, and Lab 9.2's `modernize.migration.losses`, the incident's migration and `modernize.parallel`, on the stated inputs. `labs/ch09/L9.1-spec-to-reviewed-pr/tests/test_answers.py` and `labs/ch09/L9.2-legacy-refactor-characterization/tests/test_answers.py` lock the results.

## Recall

**1. Characterization tests.** A characterization test records what existing code actually does on chosen or generated inputs, so that a later change can be compared with it. A test written from a specification checks what the code should do; its expected values come from the spec or a hand calculation (Chapter 8). A characterization test's expected values come from running the old code, deliberately: the old code is the oracle for the new. It must pin behaviour you think is wrong because the purpose of the refactor is to change nothing; deciding that a behaviour is a defect is a separate decision, with its own spec and pull request. Relay's example is the spam mark suppressing security notices: characterized, not endorsed. Full marks need the distinction between "pinned" and "endorsed"; deduct for answers that say characterization tests are self-confirming and therefore useless.

**2. Kinds of claim (any three).** Who uses a table (strings in `src/` naming it; misses SQL built at run time from parts). Who calls a function (calls by name or attribute, with `ast`; misses calls through a variable, `getattr` or a callback). What tests expect (a pattern over `tests/`; misses the same assertion written another way, such as `len(store.outbox()) == 0`). What a constraint allows (the `CHECK` in a `CREATE TABLE`; misses a constraint added later by a migration). What a package imports (import statements, relative imports resolved; misses dynamic imports and plugins). What a contract lists (the OpenAPI file; says nothing about whether the service matches it). The general point earns credit: a static check can show a claim false but cannot prove it true.

**3. Automation bias.** The tendency to accept an automated system's output with less scrutiny than a person's, and to look less hard for evidence against it, through errors of commission and of omission. Features of the incident (any two, each with a control): a change too large to read (4,067 lines; the size limit and PR01); tests written by the same agent as the code, so green tests vouched for nothing (approved tests committed first; PR02 and PR03); a fluent description with no evidence ("All tests pass"; the description template with file and line for each claim); a review rate of 407 changed lines a minute (PR08 and recording review time); no question asked of the author (checklist section H).

**4. Worktrees.** A worktree shares the repository's history, object store and refs with the other worktrees; it has its own working files, its own index and its own checked-out branch. Separate worktrees stop agents overwriting each other's files while they work. They do not stop two branches changing the same lines, which conflict when merged, or changing related code that breaks when combined (a semantic conflict). Partitioning by file, integration order and tests after each merge address those.

## Apply

**5. Pull-request check.** Outside `tests/`: 150 + 30 = **180** changed lines; in all: 120 + 180 + 10 + 4 = **314**. Both within the limits (200 and 400), so no PR01. Findings: **PR02** (blocking): `tests/test_old.py` existed before and changes in the commit that changes `src/relay/a.py`. **PR09** (warning): code changes with no docs change and no "Docs:" line. PR03 does not fire, because a tests-only commit comes first. The review rate is 314 / (40/60) = **471** lines an hour, under 500, so no PR08.
- (a) In 30 minutes: 314 / 0.5 = **628** lines an hour, so **PR08** joins PR02 and PR09.
- (b) With the `tests/test_old.py` change in the first commit, the sizes are unchanged and **PR02 disappears**; only PR09 remains. A strong answer adds that moving the change does not make it right: the reviewer must still read why an existing test's expectation changed, now in a commit where it is visible on its own.

**6. The incident's migration.** `WHERE muted_types <> ''` keeps only users 1, 2 and 5; users 3 (NULL) and 4 (empty) are not copied. Splitting on commas turns user 1's list into one type, "comment;mention", and user 5's into "all;comment"; user 2's "Digest" is lowercased and kept.
- Opt-outs before (as the legacy code reads them): user 1 {comment, mention}, user 2 {digest}, user 5 {all, comment}: **5**. Lost: **4** (users 1 and 5 lose both of theirs), affecting **2 users**; only user 2's survives.
- Spam marks before: users 3, 4 and 5: **3**. Lost: **2** (users 3 and 4, whose rows were not copied); user 5's survives because its row was copied.
- At 09:00 UTC on 9 December, a comment email: user 1 now gets one (its "comment" opt-out is gone); users 3 and 4 now get one (their spam marks, from 1 and 5 December, would still have suppressed it). User 2 got one before and after. User 5 gets none in either case: its spam mark of 20 November is still within 30 days. **Users 1, 3 and 4.**

Deduct for counting "comment;mention" as a surviving opt-out: it is stored, but it matches no notification type.

**7. Waves and order.** Waves: **{A}, then {B, C, E}, then {D}**. Integration order (dependencies first, ties by wave then ID): **A, B, C, E, D**. Predicted overlaps: **C and E both touch `c.py`**, in the same wave. B and D both touch `a.py`, but D depends on B, so D's agent starts from the tree after B has merged and edits B's version; that is ordinary sequential work, not a parallel overlap. A strong answer suggests merging C and E into one task, or making E depend on C, and notes that A's `a.py` is also touched by B and D in sequence, which is fine.

## Design

**8. Review policy for a team whose agents open most pull requests.** Marking notes. A strong answer includes:
- A size limit enforced before review (for example 200 changed lines outside tests and 400 in all), with exceptions requested in the description and approved by a code owner, and generated data excluded explicitly rather than by habit.
- Pre-review checks run from a pinned copy: size, tests-first commits, no existing test edited in a code commit, migrations with migration tests, routes with contracts, spec changes in their own pull request.
- Code owners for tests, with security-relevant tests, oracle markers and properties owned by the security team, and the check listing every marker and property changed.
- An independent reviewer on every pull request: someone who neither opened it nor wrote a commit, counting an agent's commits as the person who ran it (Lab 9.1's PR10), and the review policy itself merged, and reviewed, before the work it governs.
- AI-assisted review as a second reader that must quote evidence for each checklist item; it never approves, and its comments are checked like an agent's claims. Prompt injection through pull-request content is named as a risk (Chapter 12).
- Measurement: review rate, time to first review, defects found after merge that review could have caught, and rework rate (Chapter 1); a review queue that grows is treated as the constraint, answered with smaller or fewer pull requests, not faster reading.
- "The author can explain every change": the person who directed the agent is the author of record, answers at least one question per review about a line they did not type, and rewrites by hand what they cannot explain.

**9. Modernizing the export job.** Marking notes. A strong answer includes:
- A corpus shaped like production: export sizes up to the 50,000-task limit, both CSV and JSON, jobs started during a deploy, retries, the 5-concurrent-jobs limit, expiry after 7 days, Guests and permissions; synthetic data only, classified like production (Chapter 8).
- Characterization of outputs (files, status transitions, errors) with the old code as oracle where it can run, and tags by behaviour; the deploy-time issue characterized, then fixed through its own spec.
- Steps: import unchanged and characterize; extract a seam (for example the job's state machine); new storage or queue with writes to both and a proved migration; shadow reads; switch reads; retire the old path later. Each with a rollback that is not a restore.
- A partition for two agents that touch disjoint files (for example the state machine and the file writer), with the shared interface fixed first.
- Stop signals: a characterization difference the agent cannot explain, an edit to an approved test, a change outside the task's files, a migration without a proof.

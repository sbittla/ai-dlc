# Drift-check record

Copy to `evidence/drift-record.md` and complete every section.

## 1. Results on the seeded scenarios

Paste the table from `python -m driftcheck.report ... --run-tests`. State how many structural and behavioural drifts were seeded, and how many the gate and the test suite each found.

## 2. Drift the tests missed

Name each scenario where the gate failed and the test suite passed. Why did the tests not see it?

## 3. Drift the gate cannot see

For scenarios 07 and 08: what changed, which check caught it (if any), and what would have caught the one nothing caught.

## 4. Your own scenario

Describe the drift you seeded (step 5), what you expected each check to report, and what they reported.

## 5. The gate in CI

- Where the job runs, what it blocks and what it only warns on.
- Why exit status 2 (cannot check) must fail the build.
- Who may change the drift policy, and how that change is reviewed.

## 6. AI-use disclosure

What an assistant or agent produced, and how you checked it.

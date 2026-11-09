# Relay review checklist (agent-written or not)

Answer every item pass, fail or not applicable, and quote the file and line that decides it. "Looks right" is not an answer. The pull-request check (`prkit.prcheck`) has already run; this list is for what it cannot see.

## A. Size and shape
1. The pull request does one task, and its description says which.
2. At most 200 changed lines outside `tests/`, and 400 in all (PR01). If not, it is split before review.
3. The approved tests are in a commit before the code, and the code commit changes no existing test (PR02, PR03).

## B. Correctness against the spec
4. Every behaviour the description claims is in the spec section it names, and every changed behaviour is in the description.
5. Boundaries: each new comparison is checked against the spec's boundary (`<` or `<=`, inclusive or not).
6. Every new function that reads a time takes it as an argument; nothing reads a clock.

## C. Tests and oracles
7. Each new expected value comes from the spec or a hand calculation beside it, never from running the code.
8. Every `# oracle:` marker and `@for_all` property added or changed is read by a code owner of the tests (PR07).
9. A test that failed before the change fails for the right reason, and none was deleted, skipped or loosened.

## D. Data and migrations
10. A migration copies every row and proves the copy before it drops anything, and its test says how (PR04).
11. A downgrade exists, or the description says why the rollback is a configuration change instead.
12. No `WHERE` clause in a copy, unless the description says which rows are left behind and why.

## E. Security: the patterns models get wrong
13. Every route checks the caller's role and the object's project on the server, and an unviewable object looks absent (404).
14. Input is validated at the boundary; SQL passes values as parameters, never by string building, and builds identifiers (table and column names) only from module constants; no `eval`, `exec`, `pickle` or shell.
15. No secret, token or Confidential field reaches a log, an error, a message or a test fixture.
16. No new network call, file access or dependency, unless an ADR allows it; every package name is checked against the registry.
17. No change to security tests, CODEOWNERS, branch protection or scanner configuration without the owning team's review.

## F. Operability
18. Failures are visible: a failed background step is counted and makes its health check fail, rather than being swallowed.
19. Retries and repeated runs are safe: idempotency keys, unique constraints, or a recorded reason why not.

## G. Docs and decisions
20. The spec, OpenAPI description and ADRs that the change depends on are merged, or in this pull request where allowed.

## H. The author can explain it
21. The person who opened the pull request can explain every changed line without the agent, and the reviewer has asked them about at least one.

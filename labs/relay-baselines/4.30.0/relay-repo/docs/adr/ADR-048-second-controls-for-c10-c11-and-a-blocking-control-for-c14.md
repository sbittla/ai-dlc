# ADR-048 — Test runs with no network for C10 and C11, and human labels for judge-injection items for C14

Status: accepted
Date: 2027-03-19
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), tomas.b (support), priya.n (platform on-call)
Links: ESC-N03, ESC-N07, ESC-N01
Related: ADR-013, ADR-025, ADR-027, ADR-032, ADR-034, ADR-035, ADR-044
Revisit when: the helper gains a tool that runs code other than tests; a judge grades anything that decides a
release outside the triage gate; or the coverage gate's catalogue gains an exfiltration class. Review by
2027-09-19 in any case.
Supersedes: none.

## Context

Chapter 12's coverage gate (relay-coverage-gate-v2) fails on three classes. C10 and C11, data out through an
agent's network request, rest on the egress proxy alone, because the spec-to-PR helper's `run_tests` runs code
the agent wrote and that code reaches the network through the proxy. C14, a judge's verdict set by the text it
grades, has no blocking control: separating the answer from the judge's instructions only lowers how often a
judge obeys. Owners and dates: sam.o for C10 and C11 by 2027-04-30; aisha.r with tomas.b for C14 by 2027-03-31.

## Options considered

### Option A — Run every agent test run in a container with no network; decide judge-injection items by a person's label

### Option B — A broker for GitHub calls, so the proxy can refuse every GitHub host to agent sandboxes; a stronger judge prompt

### Option C — Remove `run_tests` from the helper; stop using a judge in the triage gate

## Decision

Option A.

- `tools/sandbox_run.py` builds the only command `run_tests` may use: a container with `--network=none`, a
  read-only root and read-only mounts, a non-root user, every capability dropped, no credential in its
  environment, and time, process and memory limits (`deploy/test-sandbox/policy.json`, SB001-SB007).
  Dependencies are installed from the lock file with hashes before any agent code exists, into a mount the
  container reads. Its failure domain is the container runtime's network isolation, disjoint from the proxy's.
  The helper's job binds `run_tests` to it (`.github/workflows/spec-to-pr.yml`), and
  builds the test environment inside the same image before any agent code exists. The job runs on an ephemeral
  runner in the agent sandbox subnet, whose only route out is the egress proxy (ADR-045's exception), so the proxy
  counted for C10 and C11 is on the helper's path: on a GitHub-hosted runner it would not be.
- `relay.release.judged` decides which verdict a release may rest on. An item in `kind:adversarial` or
  `kind:judge-injection`, or carrying a grader directive, is decided by a person's label; the judge's verdict on
  it is recorded and never read; a missing label makes the gate exit 2. A label counts only with its labeller and the
  SHA-256 of the answer it judged; a label for an earlier answer is missing. Labels live in `evals/`, a pipeline
  path owned by `@relay/security`. Its failure domain is that module and the labelling queue, disjoint from the
  judge.
- Both are counted by the coverage gate only after deployment evidence: the helper's job running tests through
  the sandbox, and the evaluation gate reading human labels in the pipeline's `eval` stage.

## Consequences

- Tests that need the network cannot run in the helper's runs. Relay's suite needs none: its HTTP tests bind to
  127.0.0.1, which the container keeps.
- A planted grader directive in an item outside the human-labelled slices still reaches the judge if the pattern
  misses it. The slices grow with every judge-injection case found, and judge isolation stays as mitigation.
- tomas.b's team labels about 40 items a release (the adversarial slice plus flagged items), about an hour.

## Rejected alternatives

### Option B — A broker for GitHub calls, so the proxy can refuse every GitHub host to agent sandboxes; a stronger judge prompt
Rejected because: the broker is a new service to build and secure, which ADR-035 carried as larger work, and a stronger prompt is still a request to a model, which is mitigation rather than a control.
Revisit if: an agent needs to run code that legitimately needs the network, where the broker becomes the only way to keep two controls.

### Option C — Remove `run_tests` from the helper; stop using a judge in the triage gate
Rejected because: the helper's value is a tested pull request, and the judge grades free-text answers no exact-match rule can score.
Revisit if: the sandbox proves unworkable for the helper's tasks in its first month.

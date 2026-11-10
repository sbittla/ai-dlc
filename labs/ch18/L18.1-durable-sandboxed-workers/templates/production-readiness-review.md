# Production-readiness review: an agent run as a worker

Agent: `________________` (registry entry: `governance/agents.json`) Owner: `________` Date: `__________`
Release under review: Relay `______` Reviewers (two people, one from `@relay/security`): `________`, `________`

Mark each row **met**, **not met** or **not applicable**, with the evidence (a file, a test, a drill, a log line).
A row with no evidence is not met. Gate G5 also needs the release to arrive through the hardened pipeline with
signed, policy-verified artefacts (Chapter 15); that row is copied from the pipeline's record, not argued here.

| # | Question | Status | Evidence |
| ---: | --- | --- | --- |
| 1 | Does every job have a business key, so a repeated delivery is the same job? | | |
| 2 | Is every effect outside Relay in the effect ledger under a natural key, passed to the provider as its idempotency key? | | |
| 3 | Does the worker extend its lease between steps, and stop before its next effect when it has lost the job? | | |
| 4 | Is there a dead-letter state with a reason, an alert on it, and a named person who may redrive? | | |
| 5 | Are rate limits, timeouts and dependency errors classified, retried with jittered backoff, and guarded by a breaker? | | |
| 6 | Can a person cancel a job, and does it stop between steps? | | |
| 7 | Does agent-written code run only in the sandbox, with no environment, no network beyond the allowlist and limits? | | |
| 8 | In the cloud, does that code run in a separate task with no role beyond what it needs and no route but the proxy? | | |
| 9 | Does the agent run under its own identity with 15-minute tokens, verified on every call against the shared registry state? | | |
| 10 | Has the kill switch been tripped in a drill from another process, and was the next call refused? | | |
| 11 | Does every tool whose results outsiders write declare `untrusted_result`, and does memory recall go through `RECALL_MEMORY`? | | |
| 12 | Is there a control outside the tool boundary for each unauthorised-action class (Chapter 12)? | | |
| 13 | Is one job traceable end to end (request, queue wait, attempts, tool calls, sandbox), with no content in the trace? | | |
| 14 | Do budgets, spend quotas and SLOs exist for the agent, with alerts on budget stops and unknown outcomes? | | |
| 15 | Which steps are deterministic code or a workflow rather than the agent, and why is the agent needed for the rest? | | |
| 16 | Signed, policy-verified artefacts deployed through the hardened pipeline (copied from the pipeline's record) | | |

Security sign-off (name, date, conditions): `____________________________________________`

Decision: **ready** / **ready with conditions** (list each with an owner and a date) / **not ready**.

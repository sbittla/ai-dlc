# Design record: the spec-to-PR helper

Author: ____________   Reviewer (not the author): ____________   Date: ____________

## 1. The task and its stopping conditions

- What the helper must produce, and what counts as handing back:
- Budget per run (steps, cost, seconds), and where each number came from:
- Stop rules (repeated failure, no progress), and why those limits:

## 2. Why each agent exists instead of deterministic code

| Step | Deterministic code, a single model call, or an agent? | Why | Evidence (report and row) |
| --- | --- | --- | --- |
| Read the task and its files | | | |
| Find files the task did not list | | | |
| Write the change | | | |
| Run tests and the pre-review check | | | |
| Review the change | | | |
| Open the pull request | | | |

## 3. The comparison (held-out split)

- Paired difference against the reference, with its interval, b, c and p, for each candidate:
- Wrong pull requests, with interval:
- Cost per run and per success; median and p90 latency:
- Where the bootstrap and McNemar disagree, and what that tells you:
- Smallest difference this dataset could detect (power), and whether that is enough:

## 4. Identities, tools and approvals

- Agent identities needed, with owner and scopes:
- Tools each agent may call, with effect and approval:
- Every high-impact action and its approval gate:

## 5. Decision and open items

- Design chosen, and the one sentence that justifies it:
- What would change the decision (revisit conditions):
- Open items, each with an owner:

## AI-use disclosure

What did an agent produce in this lab, and how did you verify it?

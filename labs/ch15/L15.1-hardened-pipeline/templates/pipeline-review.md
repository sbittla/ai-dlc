# Pipeline change review

Copy into `evidence/` and complete. A pipeline change is reviewed on its own, by someone other than its author
and other than whoever asked an agent to write it (relay-pipeline-guard-v1).

| | |
| --- | --- |
| Change (pull request or file) | |
| Written by (person or agent; who asked) | |
| Reviewer and team | |
| Date | |

## What the lint says (PL001-PL010)

| Finding | Accept, fix or reject | Why |
| --- | --- | --- |
| | | |

## What the gate diff says (GD001-GD008)

List every required check whose job, steps, condition, trigger or permissions changed. For each weakening, the
reason and the `@relay/security` reviewer.

## Credentials and triggers

- How does each job reach the cloud? (OIDC from which environment, to which role?)
- Which events start the workflow, and can anyone without write access cause one?
- Which jobs can mint an OIDC token, and is each bound to a protected environment?

## AI-use disclosure

What did an agent draft, and how did you check each part of it?

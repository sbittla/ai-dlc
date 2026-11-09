# Kill-switch drill record

Copy to `evidence/drill-record.md` and complete one record per drill. A drill is run against a simulated agent;
never trip a production agent to practise.

| Field | Value |
| --- | --- |
| Drill id and date | |
| Agent identity and revocation path (`ci-job` or `ecs-task`) | |
| Who ran it; who observed | |
| Alert (rule, time) | |
| Trip (actor, time) | |
| Relay: last accepted request; first refused request; seconds from the alert | |
| Relay: outcome of a token exchange after the trip | |
| Cloud: quarantine attached (time); first `AccessDenied` for the role (time) | measured / simulated / assumed |
| Running work stopped (tasks or workflow runs; time) | measured / simulated / assumed |
| Requirement (60 s from the alert) met? On which side was it measured, and which side was assumed? | |
| Restore: who restored, who reviewed, time; old tokens still refused? | |
| Findings, each with an owner and a date | |

## What an agent produced

Name any part of this drill an agent prepared (scripts, the simulated load, this record) and how you checked it.

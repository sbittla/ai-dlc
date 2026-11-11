# Spec-to-PR agent platform: specification

Status: approved
Approved: 2027-07-30 by the product owner

## Goal

Tasks at risk of missing their deadline reach a person who acts.

## Non-goals

Mobile clients, multi-region deployment, billing.

## Acceptance criteria

- B-AC01 Given a task near its deadline with no acknowledgement, when the worker runs, it is marked at risk.
- B-AC02 Given an at-risk task, the summary and route are produced, or the fallback route within 10 s.
- B-AC03 Given no action within the policy's window, the escalation goes to the next person.
- B-AC04 No action leaves the system without an approval and a policy check.
- B-AC05 Cost per task stays below the target set at CP0.
- B-AC06 Text from tasks is treated as data; no instruction in it changes a route.

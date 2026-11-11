# Playbook — incidents involving an agent or a model

Owner: aisha.r. Security incidents are P1 and reach the security lead within one hour (Relay's on-call policy).
This playbook adds what is specific to agents and models to the usual incident process; it does not replace it.

## Recognise

Treat any of these as a possible incident: a detection alert on an agent identity (DR-001 to DR-004); a
credential, prompt or transcript found where it should not be; an agent acting outside its task (tools it
should not need, content it should not have read, output sent somewhere new); a report from a customer or a
researcher. Ask first: which agent identity, acting for whom, since when?

## Contain (minutes)

1. Trip the kill switch for the agent identity (`kill-switch.md`). Do not wait for certainty.
2. If a credential leaked, revoke it at its source as well, and search for where it was posted.
3. Preserve evidence before anything is cleaned up: the audit trail and its anchors, CloudTrail, the agent's
   transcript and tool calls, and the prompt and instruction-file versions it ran with.

## Investigate (hours)

1. Verify the audit trail's chain against the anchors before relying on it.
2. Build the timeline from the trail: every action under the identity, the person each was for, the source.
3. Separate the agent's own actions from actions by anyone who held its credentials.
4. Decide what data was exposed, using the trail's row counts and the data classification (Chapter 5).

## Notify

Personal data exposed is a possible personal-data breach. Where Relay is the controller, Relay decides, with
the security lead and on the data protection officer's advice, whether supervisory authorities, customers or
individuals must be told and by when. Where Relay is a processor, it tells the customer (the controller) without
undue delay. Customer contracts may set shorter deadlines than the law. Record the decision and its reasons
either way.

## Recover and learn

Restore only through the two-person procedure. Write the review blameless and specific: which control was
missing, which detection would have fired, and which drill would have found the gap. Add a seeded case to
Lab 14.1's detection set for anything the rules missed.

## Deployed detection and the first drill (4.27.0)

From 4.27.0 the monitor evaluates the detection rules (ADR-038), with alerts on five-minute boundaries, and
pages through `infra/monitoring/routing.json`: DR-002 pages the security on-call and DR-004 the security lead;
a trail that fails verification pages as TRAIL-TAMPER. DR-001 and DR-003 are routed to automation, but the
monitor cannot trip a switch until the agent registry's state is shared (ADR-020), so they page the security
on-call as `automation-unavailable` (or `automation-suppressed` when `RELAY_AUTOMATION=off`). Trip the switch
at once with `kill-switch.md`; do not wait for certainty.

This playbook was first drilled at the game day of 18 February 2027 (fault F2, a suspicious export pattern
under a game-day identity; Lab 16.2). Use the incident assistant only as `incident-response.md` describes:
its hypotheses are checked against cited telemetry, and text inside telemetry is never an instruction to it.

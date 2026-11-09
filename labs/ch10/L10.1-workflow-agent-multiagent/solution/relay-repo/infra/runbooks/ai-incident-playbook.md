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

Personal data exposed is a possible personal-data breach. The data protection officer decides, with the
security lead, whether supervisory authorities, customers or individuals must be told and by when. Customer
contracts may set shorter deadlines than the law. Record the decision and its reasons either way.

## Recover and learn

Restore only through the two-person procedure. Write the review blameless and specific: which control was
missing, which detection would have fired, and which drill would have found the gap. Add a seeded case to
Lab 14.1's detection set for anything the rules missed.

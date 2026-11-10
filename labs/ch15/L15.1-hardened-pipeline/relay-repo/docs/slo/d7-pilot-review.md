# D7 review: the flood cap after the pilot's first month

Date: 2027-02-05. Decided by: lena.k (product owner, owner of the open question). With: aisha.r (security),
tomas.b (support), sam.o (tech lead). Evidence: Lab 16.1's `python -m slolab.report pilot`, over January's
generated pilot data for both pilot workspaces (4 to 31 January 2027). The pilot ran in production Relay,
outside the teaching snapshot; the non-production environment carries no traffic.

## The question

D7 set the flood cap at 20 escalation emails per target per hour (ESC-N04), to be reviewed with a month of
pilot data. PRD v1.1 carried one open question to this review: should P1 escalations be exempt? As written, a P1
email over the cap waits for the hourly summary, which works against G1. Webhook events are never capped.

## Evidence

- 2,556 steps fired and 2,509 emails were sent; the cap held 47 emails: 44 for P3 and 3 for P1.
- Two target-hours went over the cap. One was a bulk import on 12 January that made a P3 rule fire 64 steps
  for one person in 39 minutes; the cap did its job. The other was the platform outage of 21 January, when one
  on-call user received 23 P1 escalations in an hour.
- All 3 held P1 emails were for that user during that outage. The user first acknowledged an outage
  escalation at 10:03:05, and all 3 held tasks were acknowledged within 10 minutes of being held. All 3
  webhook events were delivered to the customer's paging tool.
- Outside the outage, no person received more than 2 P1 emails in any hour.
- 399 of 457 P1 steps (87.3%) were acknowledged within 10 minutes.

The pilot data is small: one month, two workspaces, one outage. It shows that the cap did not delay anyone's
response in the pilot. It cannot show that a held P1 never matters.

## Decision

**Keep the cap for P1; no exemption.** Exempting P1 would let anyone who can set a task to P1 send unlimited
email to a colleague, which is the abuse ESC-N04 exists to stop. The pilot gave no case where the cap delayed a
response. To keep a held P1 from being silent, 4.27.0 adds AL-006: a P1 escalation held by the cap and not
acknowledged within 10 minutes pages the platform on-call, who calls the workspace's Owner.

No change to ESC-SPEC-1's behaviour follows, so no spec version changes. PRD v1.2 should record this outcome
and close the open question (lena.k).

## D8, reviewed at the same meeting

D8 set ESC-N09's targets for the pilot: 95% of steps within 60 seconds each week, and a page after 5 minutes
without a completed pass. Week 3 failed at 90.5%, because the evaluator stalled overnight on 19 January and no
alert existed. The targets stay; the stall page (AL-001) now exists, and RF-001 and RF-002 check both weekly
and continuously. ESC-AC29 and ESC-AC30 stay outside ESC-SPEC-1 as runtime checks. D8 is reviewed again with
D7, by 2027-04-30.

## Revisit if

Any AL-006 page fires; or a P1 is held outside a declared incident; or the pilot grows beyond two workspaces.
Review again with the pilot's third month in any case, by 2027-04-30.

# ADR-033 — The email delivery adapter: one module admitted to the network, recipients only from Relay's directory

Status: accepted
Date: 2027-02-09
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), lena.k (product)
Links: D6, D7, ESC-N05, ESC-N07, ESC-N10, CON-1
Related: ADR-007, ADR-011, ADR-016, ADR-018, ADR-032
Revisit when: a second email kind is added to the contract, Relay changes email provider, or webhook delivery
needs its own adapter. Review by 2027-08-09 in any case.
Supersedes: none.
Adapter module: `relay.delivery.email_smtp`

## Context

The escalation engine writes emails to its outbox and sends nothing (ADR-011). ADR-007 said each delivery
adapter would be one module, admitted to the network by its own ADR and a one-line change to the
architecture rule. Spec 1.2.0 says an adapter must accept every email kind the contract lists, including
`rule_notice`, and ESC-R10 says suppressed addresses belong to the email adapter.

Chapter 12's red team adds a security reason to keep the adapter narrow. An adapter that sends wherever a
message says is a way out for anything that can write a row: a steered agent, or a bug. The adapter must
not let message content choose a recipient or carry an address outside Relay.

## Options considered

### Option A — One adapter module that resolves recipients from the directory, checks every link, asks relay.notify, and records every outcome

### Option B — Let the engine write the address into each outbox row and send it as written

### Option C — A paid transactional messaging service with its own templates and recipient lists

## Decision

Option A.

- `relay.delivery.email_smtp` is the only module outside `relay.service` that may import a network package.
  `tests/test_architecture.py` (FF004) checks that the networked modules are exactly
  `relay.delivery.ADAPTERS`, one per ADR, and that this ADR names its module.
- It accepts `escalation`, `summary` and `rule_notice`, the contract's three kinds.
- The address comes from Relay's directory by user ID (ESC-N05, D6). A message for a user with no address
  is refused, never sent somewhere else.
- A subject or body holding any address outside `link_base` is refused as `foreign_link`. The engine writes
  only Relay links and no task content (ESC-N07), so such a row did not come from the engine.
- It asks `relay.notify` as for a security notice: only a spam mark suppresses an escalation (ESC-R10). A
  muted type never silences a page.
- Every outcome, refusals and suppressions included, goes to the `email_delivery` table. A provider error is
  retried on the next pass, three attempts in all.

## Consequences

- No new dependency: `smtplib` and `ssl` are standard library (ESC-N10).
- ESC-AC16's warning on the task and the rule's page needs the service to read `email_delivery`; that route
  change is carried to the service's owners, with the database grant for the new table.
- The flood cap (D7) stays in the engine, which decides what is written; the adapter does not re-count.
- Webhook delivery is not part of this ADR. It needs the webhook secret in the worker's configuration.

## Rejected alternatives

### Option B — Let the engine write the address into each outbox row and send it as written
Rejected because: anything that can write an outbox row could then choose where Relay sends mail, and addresses are Confidential data that the outbox does not need.
Revisit if: never; recipients are always resolved at the boundary.

### Option C — A paid transactional messaging service with its own templates and recipient lists
Rejected because: ESC-N10 allows no paid messaging beyond email, and a second copy of recipient lists outside Relay could drift from the directory.
Revisit if: email volume outgrows the provider's SMTP limits.

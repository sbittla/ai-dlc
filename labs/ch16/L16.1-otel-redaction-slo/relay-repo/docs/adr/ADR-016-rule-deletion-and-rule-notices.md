# ADR-016 — Deleting escalation rules, and notices when a P1 rule is silenced

Status: accepted
Date: 2026-12-10
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), lena.k (product), priya.n (engineering)
Links: D2, ESC-N03, ESC-N06
Related: ESC-AC25, SEC-08, ADR-009, ADR-011, ADR-019
Revisit when: a customer asks to undelete a rule or reuse an ID; or the delivery adapters (Chapter 12) need notices on a channel other than email; or rule notices are themselves abused to flood the Owner and Admins.

## Context

Spec ESC-SPEC-1 1.1.0 deferred rule deletion and ESC-N06's loud notices, and ADR-009 recorded "no delete route
yet". ESC-N06's abuse case is a compromised account that quietly makes P1 escalations go nowhere. Deleting a P1
rule does that, and so does changing it: to P4, to a longer delay, or to targets nobody reads. ESC-AC25 asks that
the Owner and both Admins receive an email naming the rule and the Admin within 5 minutes.

Impact analysis of the 4.21.0 code (Lab 9.1) found four places a deletion touches: `esc_audit`'s outcome is
constrained to 'saved' or 'refused'; the hour's summary looks a held step's rule up by ID and, for a missing rule,
links to project 0; the outbox is read by tests that expect only escalation messages; and the refusal matrix has
a 405 row for DELETE.

## Options considered

### Option A — Soft delete: keep the row with `deleted_at`, retire the ID, and write notices in the same transaction

### Option B — Hard delete: remove the row; keep the rule only in the audit entry

### Option C — Soft delete, with notices written by the next evaluation pass

## Decision

Option A. `esc_rules` gains `deleted_at` (schema version 2, ADR-019). `rule_documents` and therefore `run_pass`
see live rules only; `rule_document(..., include_deleted=True)` lets the hour's summary still name and link a
deleted rule. A deleted rule's ID is refused by `save_rule` with 409, because `esc_fired` keys steps by rule ID
and a reused ID would inherit the old rule's fired steps. Deleting a P1 rule, and replacing a rule that is P1
before or after the change, writes one `rule_notice` email per Owner and Admin in the same transaction as the
change, so the change cannot commit without them. Creating a rule sends no notice: it cannot silence anything
(lena.k, 2026-12-10). Notices name the actor by role and user ID, because user names are Confidential.

## Consequences

- ESC-AC25's 5 minutes is met at commit time; the email adapter's delivery time is Chapter 12's to measure.
- Rollback: reverting the code to 4.21.0 keeps the soft-deleted rows, which 4.21.0 lists again but never fires;
  rolling forward finds them still deleted. After the first deletion the schema is not downgraded (ADR-019).
- The route answers 404 for a project the caller cannot view, before the role check and with no audit entry, as the
  escalation routes' policy requires; 4.22.0 applies the same order to `PUT`, which answered 403 in 4.21.0.
- The outbox now holds a third email kind. No adapter consumes it yet; Chapter 12's adapters must accept every
  kind the contract lists (spec 1.2.0, Contracts).
- Rule notices are not escalation emails, so the flood cap does not hold them. A burst of rule changes could send
  the Owner many notices; that is the revisit condition above.
- The service's notice links use the workspace's web address; production passes its own base (Chapter 13).

## Rejected alternatives

### Option B — Hard delete: remove the row; keep the rule only in the audit entry
Rejected because: the hour's summary would lose the rule's project and name, and a reused ID would inherit fired steps; recovering a rule would mean replaying the audit log.
Revisit if: retention rules require rule documents to be erased, not kept.

### Option C — Soft delete, with notices written by the next evaluation pass
Rejected because: a deletion could commit and the notice never follow if the worker is stalled, which is exactly when an attacker would act.
Revisit if: notices need data only the pass has.

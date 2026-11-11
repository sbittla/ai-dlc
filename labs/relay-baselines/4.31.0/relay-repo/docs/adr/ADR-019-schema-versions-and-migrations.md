# ADR-019 — Schema versions for module-owned tables, and migrations that prove their copies

Status: accepted
Date: 2026-12-11
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N03, CON-2
Related: SEC-09, ADR-007, ADR-011, ADR-014, ADR-016, ADR-018
Revisit when: Relay moves to PostgreSQL (ADR-014's future adapter), where columns and constraints change in place and a migration tool may be worth its dependency; or a migration takes long enough to block the deploy train.

## Context

Until 4.22.0 every module created its tables with `CREATE TABLE IF NOT EXISTS`, which cannot change an existing
table. Rule deletion needs a new column and a wider CHECK constraint on `esc_audit`, and SQLite can change a CHECK
constraint only by rebuilding the table. The notification module needs its data copied from a legacy table. The
opening incident of Chapter 9 was a migration that copied with a filter, never checked the copy, and dropped the
original in the same change.

## Options considered

### Option A — A version table per module, migrations in the module, and a proof before any drop

### Option B — A migration tool with versioned scripts

### Option C — Keep `IF NOT EXISTS`, and add columns only

## Decision

Option A. Each module that owns tables records its schema version in its own table (`esc_schema` for escalation);
a database without one is version 1. Opening a store migrates it, inside BEGIN IMMEDIATE, reading the version
again under the lock, so two processes starting together migrate once. A migration that rebuilds a table copies
every row and proves the copy before it drops anything: the same count, and no row in one table but not the other,
comparing every column of the new table as read from the database, not the column list the copy used. A downgrade
exists for every version and refuses, changing nothing, if it would lose a row. A migration that moves data
between tables (the notification module's) never drops the source in the same change.

**Rollback for escalation schema version 2.** Rolling the code back to 4.21.0 leaves the schema at version 2, which
4.21.0 opens: its `CREATE TABLE IF NOT EXISTS` statements change nothing, and it ignores `deleted_at` and
`esc_schema`. Its routes then list deleted rules again. None of them fires, because 4.21.0's worker runs no
evaluation pass (ADR-017 is 4.22.0's), but an Admin could edit one. Rolling forward to 4.22.0 finds every deleted rule
still deleted. The schema downgrade is for use only before the first deletion; once a rule has been deleted, the
plan is to roll forward, not to restore. Lab 9.1's `tests/test_rollback.py` tests each of these with both versions'
code.

## Consequences

- Every test that opens an escalation store exercises the migration from version 1 to 2.
- Migrations live next to the tables they change and are reviewed with them, by the module's code owners.
- A dropped table is a separate, later change with its own review, after the rollback window.
- Large tables will make rebuilds slow; SQLite's limits are recorded in ADR-014's PostgreSQL revisit condition.

## Rejected alternatives

### Option B — A migration tool with versioned scripts
Rejected because: it is a dependency (FF005), and Relay has two modules with migrations; the proof rule matters more than the tool.
Revisit if: Relay moves to PostgreSQL or gains a third module with migrations.

### Option C — Keep `IF NOT EXISTS`, and add columns only
Rejected because: the audit table's CHECK constraint cannot be widened by adding a column, and storing deletions as 'saved' would make the audit log lie.
Revisit if: never.

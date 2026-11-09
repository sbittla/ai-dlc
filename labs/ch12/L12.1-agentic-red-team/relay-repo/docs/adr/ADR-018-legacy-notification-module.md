# ADR-018 — Modernizing the legacy notification module behind characterization tests

Status: accepted
Date: 2026-12-11 (amended 2026-12-15: the accepted difference, aware times, per-step rollback)
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), lena.k (product), tomas.b (support), priya.n (engineering)
Links: ESC-N10, CON-1, CON-2
Related: ESC-R10, ESC-AC16, ADR-007, ADR-019
Revisit when: the rollback window closes on 2027-01-31 (drop the legacy table, in its own reviewed change); or Chapter 12's email adapter needs preferences the new tables do not hold; or a characterized behaviour is changed by a spec.

## Context

Relay's notification preferences (per-type opt-outs, and a spam mark that suppresses email for 30 days) live in
`relay/notifications.py`, written for Relay 3.x in 2023 and last changed on 2024-03-12 (Relay 3.9). It runs in
production but was outside the teaching snapshot. It has a global connection, reads the clock when no time is
passed, and stores muted types as text in two formats: "a;b" from Relay 3.0 to 3.3 and "a,b" since 3.4.

On 8 December 2026 a 4,067-line agent pull request that rewrote the module in one step was approved after a
ten-minute review. Its migration lost every 3.x opt-out and every spam mark on a user with no muted types, and
then dropped the legacy table (Chapter 9, opening incident). The table was restored from backup on 9 December.

## Options considered

### Option A — Strangle it: import it unchanged, characterize it, and replace it in small reviewed steps with a rollback at each step

### Option B — Rewrite it again in one change, more carefully

### Option C — Leave it in production, unchanged and untested

## Decision

Option A, in five pull requests, each within the size limit (200 changed lines outside `tests/`, 400 in all):

| Step | Change | Rollback |
| --- | --- | --- |
| notify-1 | Import the module unchanged twice, as a working copy in `src/relay/notify/legacy.py` and a frozen copy in `tests/notify/legacy_reference.py`, and characterize it | Revert: nothing calls the new package yet |
| notify-2 | Extract the decision into a pure function, `relay.notify.decide` | Revert: behaviour is identical |
| notify-3 | New tables, a migration that proves every user's preferences before it commits, and writes to both tables | Revert; the legacy table was never altered |
| notify-4 | A compatibility layer with the legacy names, reading in shadow mode | `RELAY_NOTIFY_READ_FROM=legacy` and a restart, or revert |
| notify-5 | Read from the new tables; remove the working copy (the frozen copy stays as the oracle) | `RELAY_NOTIFY_READ_FROM=legacy` and a restart |

Every write goes to the new tables and the legacy table in one transaction until 2027-01-31, so rolling reads back
is a configuration change, not a restore. One difference from the legacy behaviour is accepted: `get_prefs` lists
muted types sorted and without duplicates (lena.k, 2026-12-15). A spam mark still suppresses security notices, and a
timezone-aware time still counts in its own zone's date, as the legacy code did; both are characterized, not
endorsed, and changing either needs a spec and its own pull request.

## Consequences

- The module joins DOMAIN in the architecture tests and is standard library only, like the rest of Relay.
- Production callers keep the legacy function names; new code takes a `NotifyStore` and calls `decide`.
- The characterization tests compare with the legacy code itself, so they can generate new cases at any time.
- The legacy table and the dual write are temporary; leaving them past 2027-01-31 is a decision, not a default.

## Rejected alternatives

### Option B — Rewrite it again in one change, more carefully
Rejected because: the 8 December change was careful by its author's standards; what it lacked was a record of what the old code did, and a review it could pass.
Revisit if: never for code with production data behind it.

### Option C — Leave it in production, unchanged and untested
Rejected because: Chapter 12's email adapter must apply opt-outs and suppressions (ESC-R10, ESC-AC16), and it cannot build on a module nobody can test.
Revisit if: the adapter is cancelled.

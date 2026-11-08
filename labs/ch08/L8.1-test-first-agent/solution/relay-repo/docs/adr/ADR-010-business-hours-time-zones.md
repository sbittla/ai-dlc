# ADR-010 — Business hours in local wall-clock time, with a dated daylight-saving table for the snapshot's zones

Status: accepted
Date: 2026-12-01
Decided by: sam.o (architect of record)
Reviewed by: lena.k (product), priya.n (engineering)
Links: D4, D10, D11, CON-1, CON-2
Revisit when: Relay deploys to an environment that provides IANA time-zone data on every host; or a rule needs a zone outside the 14 the snapshot supports; or the table nears its end on 2027-12-31, and in any case by 2027-09-30.

## Context

PRD v1.1 makes P2 to P4 rules count business hours in the rule's own zone (D4), on the days it lists (D10), as
local wall-clock hours across daylight-saving changes (D11). This closes PRD v1.0's open question owned by sam.o.
Relay's snapshot keeps one mid-November offset per zone (`relay.timezones`) so that tests run identically on every
operating system without the `tzdata` package. On Windows, Python's `zoneinfo` has no system data without it.
A fixed offset would time a Berlin P2 one hour late from 28 March 2027.

## Options considered

### Option A — A dated daylight-saving table for the 14 supported zones, 2026 and 2027, failing closed outside it

### Option B — Python's zoneinfo with the tzdata package as a dependency

### Option C — Keep the fixed mid-November offsets and document the error

## Decision

Option A. `relay/escalation/hours.py` lists, for each of the 14 zones in `relay.timezones`, its standard offset and
its daylight-saving periods in 2026 and 2027 as UTC instants. Outside those years `offset_at` raises an error, so no
step is ever timed with a guessed offset. A test checks that the table's mid-November offsets equal
`relay.timezones.OFFSETS`, and examples cover both 2026 and 2027 changes in Berlin.

## Consequences

- No new dependency; tests stay identical on every platform.
- The table is data that someone must extend before 2028 or replace with IANA data; the revisit date says when.
- Windows that contain a clock change (only rules whose hours include 01:00 to 03:45 local time in the zones that
  change) are covered by the to_utc rule and by examples, not by the property tests' generators.
- Business hours count real elapsed minutes inside local windows, so a delay ending exactly at a window's close is
  due at the close (spec B3).

## Rejected alternatives

### Option B — Python's zoneinfo with the tzdata package as a dependency
Rejected because: it adds a dependency that every lab and CI runner must install and Chapter 13 must review, for 14 zones whose rules for two years fit in one table that a test can check.
Revisit if: Relay supports zones beyond the 14, or the deployment environment provides IANA data; then a new ADR adopts it under FF005.

### Option C — Keep the fixed mid-November offsets and document the error
Rejected because: from 28 March 2027 every Berlin P2 step would fire an hour late, and in Sydney and Auckland an hour early from April, which breaks ESC-R07 silently.
Revisit if: never for production; acceptable only for a demo that runs within one daylight-saving period.

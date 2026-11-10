# ADR-037 — SLOs with multi-window burn-rate alerts, an error budget policy, and runtime fitness checks

Status: accepted
Date: 2027-02-09
Decided by: sam.o (architect of record)
Reviewed by: lena.k (product), aisha.r (security), priya.n (engineering)
Links: ESC-N09, D8, CON-1, CON-4
Related: ADR-007, ADR-017, ADR-036
Revisit when: an SLO pages more than twice a month without an incident; or traffic falls so low that 100 events
an hour is rare. Review by 2027-08-09 in any case.
Supersedes: none.

## Context

Relay's alerts were static thresholds on dashboards: page if more than 0.1% of requests failed in five minutes.
On generated January traffic (Lab 16.1) that rule opened 732 pages in 30 days, 644 of them for nothing. People
had learnt to ignore it. Chapter 6 also left runtime properties to observability: ESC-N09's 95% of steps within
60 seconds and its 5-minute stall page.

## Options considered

### Option A — SLOs per user journey, alerting on the Site Reliability Workbook's multi-window, multi-burn-rate table, with an error budget policy

### Option B — Keep static thresholds, tuned higher

### Option C — Single-window burn-rate alerts

## Decision

Option A.

- Five SLOs in `docs/slo/slos.json`: availability (99.9%) and latency (99% within 250 ms) for the API, triage
  freshness (99%), and two AI objectives, quality (80% of confirmed suggestions kept) and safety (99.5% of
  outputs pass the output check). 30-day rolling windows.
- Paging uses the workbook's table: 14.4 times over 1 hour and 5 minutes, 6 times over 6 hours and 30 minutes
  (pages), and once over 3 days and 6 hours (ticket). The AI objectives only open tickets, with a 7-day and a
  1-day window at 1.5 times and at least 100 labelled events.
- The budget policy (`docs/slo/budget-policy.md`) freezes feature releases when a budget is exhausted and asks
  for a postmortem when one event spends 20% of it.
- Runtime fitness checks RF-001 to RF-004 (`relay.telemetry.fitness`) run with the alerts: steps on time
  (ESC-AC30), a fresh heartbeat (ESC-AC29), no personal data in telemetry, no metric overflow.

## Consequences

- On the same January traffic the policy opened 2 pages, both for real outages, and tickets for the slow burn.
- A slow burn (0.5% errors for 36 hours) never pages; it tickets after 458 minutes. That is the design: it
  spends budget slowly enough for working hours.
- Quiet hours need `min_events`, or two failures out of three requests would page.
- The AI objectives detect slowly: in Lab 16.1 the quality ticket opened on the third day of a seven-day drop.
  Chapter 7's weekly sample remains the early warning.

## Rejected alternatives

### Option B — Keep static thresholds, tuned higher
Rejected because: any fixed ratio either pages on the noise of quiet minutes or misses a slow burn, and none of them says how much of the month's budget an event spends.
Revisit if: a service has no meaningful error budget, such as a batch job; use a threshold on its own deadline instead.

### Option C — Single-window burn-rate alerts
Rejected because: with one 1-hour window a page stays open for most of an hour after the problem stops; in Lab 16.1 it reset 56 minutes after the first outage, against 29 for the multi-window policy.
Revisit if: alert evaluation must be cheaper than two windows per row; the cost is small today.

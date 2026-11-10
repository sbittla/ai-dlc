# ADR-047 — Canary releases that roll back on SLO burn, and kill switches for AI features

Status: accepted
Date: 2027-03-18
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), lena.k (product), tomas.b (support), priya.n (platform on-call)
Links: ESC-N01, ESC-N09, CON-2
Related: ADR-037, ADR-038, ADR-042, ADR-044, ADR-046
Revisit when: traffic falls below what a 5% step can judge within its bake time; an automatic rollback is
judged wrong in a postmortem; or a second AI feature reaches 100%. Review by 2027-09-18 in any case.
Supersedes: none.

## Context

The train put each release in front of all traffic at once. Chapter 16's SLOs and burn rates tell the team
when users are being hurt, but by then every user is. Relay's AI features add a second kind of release: a
prompt, a route or a summary feature can harm quality without a single server error, and rolling back the
whole release to remove one feature takes longer and removes everything else too.

## Options considered

### Option A — Canary in steps with automatic rollback on SLO burn; AI features behind flags with kill switches

### Option B — Blue-green with a manual switch and a manual switch back

### Option C — Rolling replacement of tasks, watched by the on-call

## Decision

Option A.

- `deploy/rollout/canary.json` (relay-canary-v1): steps of 5%, 25%, 50% and 100% of production traffic, each held
  for 15 minutes. Each minute the canary is compared with the stable version on that minute's SLO-API-AVAIL
  and SLO-API-LATENCY (relay-slo-v1). A minute is judged only when the last five minutes hold at least 100 canary
  requests.
- Roll back automatically when, for three consecutive judged minutes, the canary's burn rate on a signal is at
  least 14.4 (Chapter 16's fast-burn rate) and the canary is worse than the stable version in the same minute. If both
  versions burn and the canary's bad share is at most twice the stable version's, the release is usually not
  the cause: hold and page, do not roll back. A canary more than twice as bad is rolled back even during a shared
  problem. A minute in which only the stable version burns is also a hold. Only a minute in which neither burns
  advances the bake clock.
- With fewer than 100 canary requests in the last five minutes, decide nothing: hold the step until there are enough. Every held minute in
  a step, for any reason, counts towards 60; at 60 the rollout is rolled back, never promoted.
- AI features are flags in `deploy/flags.json` (relay-flags-v1) read through `relay.release.flags`: off unless
  listed, off when malformed, and on only with a kill store present. SLO-TRIAGE-QUALITY (for
  `triage_routing_c`) and SLO-TRIAGE-SAFETY (for `ticket_summaries`) are compared between the workspaces that have
  the feature and those that do not. When both have at least 20 events, and the feature's cohort is worse by at
  least 5 points with a one-sided two-proportion z of 2.326 or more (p below 0.01), the automation trips that
  feature's kill switch, and the release stays. A trip is one row;
  only a person restores, with a reason naming a ticket or an incident. With Chapter 16's automation kill
  switch set (`RELAY_AUTOMATION=off`), automated trips page a person instead; the canary still rolls back its own
  rollout, which is part of the release, not an incident remediation such as Chapter 16's `deploy.rollback`.
- 4.29.0 adds the flag library and the policy only. The service and worker do not yet call
  `relay.release.flags`: wiring `FlagSet.enabled` into the worker's triage call and the suggestion view, and a
  migration for the kill-store tables, is owned by sam.o, by 2027-05-31. Until then a trip stops nothing.
- Rollback is the previous desired state, already admitted, so it needs no new approval. A rollback is recorded
  and starts a postmortem if it reached users beyond the first step.

## Consequences

- A bad release reaches about 5% of requests for a few minutes instead of all of them; Lab 15.2 measures the
  difference on its scenarios.
- Releases take at least 45 minutes from the first step to full traffic.
- A canary judged on a quiet hour takes longer, by design. The reconciler starts rollouts only in working hours
  (ADR-044).
- Database schema changes stay expand-and-contract (ADR-019), so the stable and canary versions can run side
  by side; a release whose migration cannot is refused a canary and needs a reviewed plan.

## Rejected alternatives

### Option B — Blue-green with a manual switch and a manual switch back
Rejected because: it moves all traffic at once, so a bad release still reaches every user until a person notices and switches back.
Revisit if: a release cannot run beside its predecessor, where an instant full switch with a full switch back is the safer shape.

### Option C — Rolling replacement of tasks, watched by the on-call
Rejected because: it exposes a growing share of users with no automatic stop, and it depends on a person reading graphs during every release.
Revisit if: traffic is too low for a canary step to be judged within an hour.

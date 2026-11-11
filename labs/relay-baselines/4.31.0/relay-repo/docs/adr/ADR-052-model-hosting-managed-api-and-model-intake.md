# ADR-052 — Triage stays on the managed model API in Relay's region; a self-hosted model must pass a written intake first

Status: accepted
Date: 2027-03-18
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), lena.k (product), tomas.b (support operations)
Links: CON-1, CON-4, CON-6, ESC-N01
Related: ADR-012, ADR-013, ADR-023, ADR-028, ADR-030, ADR-042, ADR-043
Revisit when: monthly triage volume passes 250,000 tickets; the provider's terms, regions or quotas change for
the model Relay uses; a customer contract requires inference inside Relay's own accounts; or an open-weight model
passes Chapter 7's gate on Relay's held-out set. Review by 2027-09-18 in any case.

## Context

Relay's triage worker and agent sandboxes call one approved model through Amazon Bedrock's runtime, over a VPC
interface endpoint whose policy admits two roles and one model ARN (ADR-013). After the refund pilot, the team was
asked whether Relay should run an open-weight model itself, for privacy, cost and quota reasons.

Lab 18.2 sized the self-hosted option with a simulated serving model of about 1.5 billion parameters on a
simulated 24 GB accelerator (configured, not measured). With continuous batching at 16-bit precision one
accelerator met the latency target up to 16 requests a second; Relay's outage peak (Chapter 17) is 0.53 a second,
3.3% of that. Two accelerators, for one spare, at an assumed $0.80 an hour, cost $1,168 a month; the managed API
cost $67.99 a month for the same 31,146 tickets at Chapter 17's configuration A, so self-hosting is 17.2 times the
cost at today's volume. With accelerators added as volume grows, continuous batching would break even at about
535,000 tickets a month (still two accelerators); static batching never would, because one accelerator at full use
costs $0.004969 a ticket against the API's $0.002183. The quality of any open-weight model on Relay's tickets
is unknown: the lab's figures are placeholders.

## Options considered

### Option A — Keep the managed API in Relay's region, through the VPC endpoint, with provider quotas and a written model intake

### Option B — Self-host an open-weight model on Relay's own accelerators

### Option C — Keep the managed API, and self-host a small model as a fallback for provider outages

## Decision

Option A.

- Triage keeps calling the approved model through Bedrock in Relay's region, over the VPC endpoint, under the
  quotas Chapter 17 set; the provider's data-handling terms are recorded in the DPIA (ADR-023).
- A request rate or token quota from the provider is a dependency limit. Agent workers treat 429 as `RateLimited`
  and their breaker holds jobs in the queue (ADR-049). The triage worker (Chapter 6's `relay.worker`) has no
  breaker yet: it retries with backoff and then hands tickets to people; giving it the same breaker is an item for
  its owner (priya.n, by 2027-06-30). Quota increases are requested before a launch, not during an incident.
- Any model Relay would load itself must pass an intake before it is used anywhere: a pinned revision, files in
  a safe format only (safetensors; never a pickle), SHA-256 of every file checked at download and at load, the
  licence recorded, Chapter 7's gate passed on Relay's held-out set, an AI-BOM entry (ADR-030) and a named
  owner. Lab 18.2's optional run shows the download and verification steps on a small public model.

## Consequences

- Nothing changes in the deployed path; the decision records why, with the volume that would reopen it.
- The intake rules apply to evaluation and test models too, so a model file never reaches a laptop or a CI job
  unverified.
- Relay depends on one provider's availability and quotas for triage. The triage queue keeps tickets when the
  provider fails, and people triage what waits (Chapter 6's degraded mode).

## Rejected alternatives

### Option B — Self-host an open-weight model on Relay's own accelerators
Rejected because: at Relay's volume it costs about 17 times the managed API before any engineering time, its quality on Relay's tickets is unmeasured, and eight engineers would run another serving stack (CON-1).
Revisit if: volume passes 250,000 tickets a month, a contract requires inference in Relay's accounts, or an open-weight model passes the triage gate.

### Option C — Keep the managed API, and self-host a small model as a fallback for provider outages
Rejected because: a fallback that is never used drifts out of evaluation, and the queue already holds tickets through an outage while people triage the urgent ones.
Revisit if: provider outages break the triage freshness SLO more than once a quarter.

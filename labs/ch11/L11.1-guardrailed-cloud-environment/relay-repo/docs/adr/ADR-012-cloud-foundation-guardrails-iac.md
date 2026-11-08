# ADR-012 — Cloud foundation: one account per environment, organization guardrails, OpenTofu with policy checks

Status: accepted
Date: 2026-11-30
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ADR-007, CON-1, CON-2, ESC-N07, ESC-N10
Revisit when: Relay runs in a second cloud provider or region; or the platform team adopts a landing-zone product that owns account creation; or plan-time checks miss a class of problem that posture management keeps finding. Review by 2027-11-30 in any case.
Supersedes: none.

## Context

On 6 November 2026 a lab environment built by hand in the shared sandbox account ran from Friday afternoon
to Monday morning: 66 hours, about $2,289 at list prices, with a model server and a database reachable from
the internet (Lab 11.1, `report incident`; composite). Nothing stopped it being created, nothing reported it
while it ran, and nobody owned it. Chapter 3's incident a month earlier had the same root: credentials and
accounts with more reach than the task needed.

Relay 4.21.0 needs a non-production environment for the service and worker of ADR-007. Eight engineers on
one rota (CON-1) must be able to rebuild, review and tear it down without a cloud specialist.

## Options considered

### Option A — One AWS account per environment under organization guardrails, OpenTofu, plan review with policy checks

### Option B — One shared account for every non-production environment, with naming conventions

### Option C — Console-built environments, documented in a wiki, with a monthly cost review

## Decision

Option A. Relay's non-production environment lives in its own account, in an organizational unit whose
service control policies (`infra/org/`) deny regions other than us-east-1 and us-west-2, compute and database
sizes beyond the small families, self-hosted model endpoints, model calls that do not arrive through a VPC
endpoint, IAM users and access keys, and switching off the audit trail. The account's own configuration is
`infra/` (OpenTofu), with remote state, a plan on every pull request, policy checks on the plan
(`cloud-policy-v1`, twelve rules) and a cost estimate, and apply only from a protected CI environment after a
person approves.

Lab 11.1 measures the checks on 16 seeded plans: they detect 12 of 14 seeded violations, fail closed on the
one change whose values are unknown until apply, raise no false alarm on the control, and miss two by design
(a wrong but specific permission, and drift made in the console after apply).

## Consequences

- Guardrails act at two times. The plan checks stop a change before apply; the SCPs refuse it at the API even
  when someone bypasses the pipeline. Neither sees the other's gaps, which is the point.
- Every resource carries `app`, `env`, `owner`, `cost-center` and `data-class` through the provider's
  `default_tags`; non-production holds Internal data at most (synthetic only).
- Two budgets: $300 a month for resources tagged `env=nonprod`, and $400 for the whole account, because a tag
  filter misses untagged spend. Budgets alert; they do not stop spending.
- CI uses OpenID Connect federation: a plan role for pull requests and an apply role for the protected
  environment, both pinned to `repo:relay-example/relay`. No stored cloud keys exist.
- The apply role's policy is broad and carries waiver W-001 (owner sam.o, expires 2027-02-26) until it is
  narrowed from the actions CloudTrail records.
- Plan-time checks do not see drift. Posture management of the live account (AWS Config rules or Security Hub
  controls) is the second control; enabling it is part of the account baseline, not of this repository.

## Rejected alternatives

### Option B — One shared account for every non-production environment, with naming conventions
Rejected because: the shared account is the blast radius of every mistake in it, as Chapter 3's deleted test database and the weekend lab both showed, and conventions cannot deny an API call the way a guardrail can.
Revisit if: the organization's account vending cannot create a new account in under a day.

### Option C — Console-built environments, documented in a wiki, with a monthly cost review
Rejected because: nothing reviewable exists before a change takes effect, a rebuild depends on memory, and a monthly review finds a weekend's spend weeks after it happened.
Revisit if: never for an environment that holds data or reaches a model; a throwaway experiment may use the sandbox account under its guardrails and a 24-hour expiry tag.

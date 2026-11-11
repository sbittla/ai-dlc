# ADR-044 — One delivery pipeline whose deterministic gates decide promotion, run verify-only until Gate G4 holds

Status: accepted
Date: 2027-03-15
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (platform on-call), lena.k (product)
Links: CON-2, CON-1, ESC-N03
Related: ADR-028, ADR-029, ADR-030, ADR-032, ADR-037, ADR-045, ADR-046, ADR-047, ADR-048
Revisit when: the first month in deliver mode ends; a gate is added or removed; or a release is deployed outside
the pipeline for any reason. Review by 2027-09-15 in any case.
Supersedes: none. Replaces CON-2 (the 15:00 UTC deploy train) from the day deliver mode starts.

## Context

Relay's releases go out on the 15:00 UTC deploy train. The gates that guard them are required status checks on
pull requests (tests, the secret scan, the supply-chain check, the security gates), plus a release workflow
that signs images, and a person who follows `infra/runbooks/deploy.md`. Nothing ties those pieces together. A
check that is skipped reports success, a scanner that writes an empty report passes the security gate, and a
hotfix image built on a laptop can be deployed by hand. On 1 March 2027 an agent's change to `ci.yml` made the
Trivy step write an empty report whenever it failed; for nine days no dependency or configuration scan ran, and
every check stayed green.

Gate G4's adversarial row is not met (Chapter 12): Chapter 12's coverage gate fails on C10, C11 and C14, and
none of the eight counted controls is deployed. Until the row holds, releases stay on the train.

## Options considered

### Option A — One pipeline: build once, four gates in parallel, then package, sign, attest, admit, deploy, verify; verify-only alongside the train until G4 holds, then deliver

### Option B — Keep the train and add the missing checks to the pull-request workflow

### Option C — Switch to the pipeline at once, before G4's row holds

## Decision

Option A.

- Stages, in order: build (once; the image digest built here is the one deployed), then test, eval, adversarial
  and scan in parallel, then release (Chapter 13's `release.yml`, called as a reusable workflow: package, sign,
  attest), then admit (ADR-046). Deployment is separate:
  a pull request sets `deploy/gitops/production.json` to the admitted digests, and on its merge `deploy.yml`
  admits again and reconciles with the canary (ADR-046, ADR-047). Only `v<digit>` tags start a release.
- Failure behaviour: every gate fails closed. Exit 1 is a failed gate and exit 2 is "cannot decide", which is
  also a failure: a missing, empty or unparseable report, a missing human label (ADR-048), or a gate whose
  input is not the release's own. Every condition that lets a later job run names `success` explicitly, so a
  skipped gate never counts as a passed one.
- Modes, set by the repository variable `RELAY_PIPELINE_MODE` (platform leads): `verify-only` runs every gate
  and admission and records the result. The train still deploys, so `release.yml` still signs and pushes the
  image, but it always adds a signed gate-results attestation, and admission refuses any image whose four gates
  did not all succeed (AD008): a verify-only signature cannot carry a failed release into production; `deliver` lets the gates decide and deploys; any
  other value deploys nothing. Verify-only starts on 2027-03-22.
- The switch to deliver needs all of: G4's adversarial row met (the coverage gate passes on the release with
  deployment evidence for every counted control); no disagreement between the pipeline and the train in the
  last ten train releases that the pipeline cannot explain; and sam.o's and aisha.r's written approval. The
  first release through the pipeline retires the train: from then on a release that does not pass the pipeline
  does not reach production.
- Four checks become required on pull requests (`governance/branch-protection.json`): `pr-check` (Chapter 9),
  `triage-eval` (Chapter 7), `coverage-gate` (Chapter 12) and `pipeline-guard` (ADR-045). The guard is
  not defined in this repository (ADR-045). Main requires the merge queue, so required checks run again after
  approvals exist.

## Consequences

- One run shows the whole decision for a release: which gate failed, on what evidence. Lab 15.1 replays the
  March incident and ten release candidates through the same stages.
- In verify-only mode the adversarial gate fails every release until the code for C10, C11 and C14 exists, by
  design. Those recorded failures are not blocks; the train is still the release path.
- The train's fixed time goes. Releases go out when they pass, which changes when people are on hand: the
  reconciler refuses to start a production rollout outside working days, 09:00 to 16:00 UTC.
- CON-2 in the driver catalogue is out of date from the switch; the catalogue's owner updates it.

## Rejected alternatives

### Option B — Keep the train and add the missing checks to the pull-request workflow
Rejected because: pull-request checks cannot see what is actually deployed, so an unsigned hotfix image or a skipped gate still reaches production.
Revisit if: the pipeline itself becomes the bottleneck and a lighter path for documentation-only changes is needed.

### Option C — Switch to the pipeline at once, before G4's row holds
Rejected because: Gate G4's adversarial row cannot be waived, and moving releases to a new path while three attack classes are short would add risk without evidence.
Revisit if: never for G4 itself; the row is the condition for the switch.

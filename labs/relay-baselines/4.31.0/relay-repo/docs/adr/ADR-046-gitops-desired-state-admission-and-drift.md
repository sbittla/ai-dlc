# ADR-046 — Production desired state in Git, admission of signed images only, and drift reported, not corrected

Status: accepted
Date: 2027-03-17
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (platform on-call)
Links: CON-2, ESC-N03
Related: ADR-012, ADR-015, ADR-028, ADR-030, ADR-031, ADR-044, ADR-045
Revisit when: production moves to a second region or to Kubernetes; a release is admitted that admission should
have refused; or a drift report is ignored for more than one working day. Review by 2027-09-17 in any case.
Supersedes: none.
Amended: 2027-04-15. Verify-only mode found a hotfix image, built on a laptop and unsigned, deployed by hand
on 14 April 2027 "just this once"; admission would have refused it. The decision is unchanged.

## Context

Chapter 13's runbook verifies a release's signature before a person deploys it. That runbook is a promise, not a
control: nothing stops a person in a hurry from deploying an image the runbook would refuse. What runs in
production is also known only from the console.
Non-production already keeps its desired state in Git (`infra/nonprod.tfvars`, Chapter 11), but production's
release version and digests were typed into the deploy command.

## Options considered

### Option A — Desired state in Git (`deploy/gitops/production.json`), an admission policy the reconciler enforces, drift reported to people

### Option B — A pull-based GitOps controller that also corrects drift automatically

### Option C — Keep the deploy runbook and add a checklist item

## Decision

Option A.

- `deploy/gitops/production.json` is production's desired state: the release, each image by digest, the flag
  document and the rollout policy. A release changes it in a pull request; nothing else may.
- The reconciler admits an image only under `deploy/admission/policy.json` (relay-admission-v1): a digest, never
  a tag; for Relay's own images a signature by `release.yml` at that release's own tag, from GitHub's issuer,
  at an X.Y.Z version, with a transparency-log entry the log signed while the certificate was valid; SBOM,
  AI-BOM and provenance attestations bound to the same digest; and a gate-results attestation saying all four
  gates succeeded. A release on the policy's revoked list is refused, so a rollback cannot reach a release later
  found vulnerable. Releases built before 2027-03-22 have no gate-results attestation, so a rollback to them is
  refused too. Third-party images only as recorded in `supply-chain/images.json`.
  The policy has no override.
- Promotion to production is the merge of the desired-state pull request, which as a pipeline path needs two
  approvals (ADR-045); its merge runs `deploy.yml`, whose `production` environment adds one required reviewer
  from the maintainers with self-review prevented. GitHub's required reviewers need one approval, not all of
  them, so the second person is the pull request's second approver. The production role trusts that
  environment's subject only.
- After an automatic canary rollback, what runs is the previous release while Git still names the new one. The
  reconciler records the rollback rather than paging drift, and the person who tagged the release opens the
  revert of `production.json` the same day.
- Drift is any difference between the desired state and what runs. The reconciler reports it hourly as a ticket
  to the platform on-call and never edits the desired state. A person either reverts the change in production or
  makes it in Git through the pipeline. Unadmitted images in production page, because they mean admission was
  bypassed.
- Non-production keeps its desired state in `infra/nonprod.tfvars`, applied through Chapter 11's protected
  environment, with the same admission check before apply.

## Consequences

- What runs is a file anyone can read and a history anyone can blame.
- An emergency fix goes through the pipeline like any release, including the desired-state pull request's two
  approvals. That fastest path is the emergency path; there is no other.
- Break-glass access (Chapter 14) still exists for the cloud account, and anything it changes appears as drift.

## Rejected alternatives

### Option B — A pull-based GitOps controller that also corrects drift automatically
Rejected because: Relay runs on ECS rather than Kubernetes, and automatic correction would undo a break-glass mitigation during an incident without a person deciding.
Revisit if: production moves to Kubernetes, or drift reports show changes that people routinely forget to revert.

### Option C — Keep the deploy runbook and add a checklist item
Rejected because: a runbook step is skipped exactly when people are in a hurry, which is when a bad image is most likely, as the 14 April hotfix later showed.
Revisit if: never as the only control; runbooks stay as the description of what the reconciler does.

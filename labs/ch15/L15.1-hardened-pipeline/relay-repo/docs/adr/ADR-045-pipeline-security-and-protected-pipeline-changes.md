# ADR-045 — Pipeline security: hosted ephemeral runners, OIDC only, least-privilege tokens, and a guard on every pipeline change

Status: accepted
Date: 2027-03-16
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (platform on-call)
Links: ESC-N03, CON-1
Related: ADR-012, ADR-020, ADR-028, ADR-029, ADR-030, ADR-044
Revisit when: Relay adds a self-hosted runner, a new cloud account or a new kind of workflow trigger; or a
pipeline change merges without the guard. Review by 2027-09-16 in any case.
Supersedes: none.

## Context

The pipeline decides what reaches production, so whoever can change it can change that decision. The March
incident's change was one line in `.github/workflows/ci.yml`, written by an agent in a coding session and
pushed by the engineer who asked for it. CODEOWNERS required a platform lead's approval for `.github/`, and it
got one: the reviewer belonged to both owning teams, so one approval of a mostly-application pull request
counted for the workflow file too. Nobody read that line as a pipeline change.

Workflows also hold the credentials that reach the cloud. Chapter 11 already federates CI to AWS by OIDC, and
the release workflow signs keylessly (ADR-030). The rest of the pipeline should follow the same rule.

## Options considered

### Option A — Hosted ephemeral runners, OIDC only, empty default token permissions, pinned actions, and a pipeline-guard required check

### Option B — Self-hosted runners inside Relay's VPC, with stored deploy keys

### Option C — CODEOWNERS alone for pipeline files

## Decision

Option A.

- **Runners.** GitHub-hosted runners: each job gets a fresh virtual machine that is discarded afterwards. One
  exception (ADR-048): the spec-to-PR helper's job runs on an ephemeral self-hosted runner, one job per runner,
  in Chapter 11's agent sandbox subnet, whose only route out is the egress proxy, so the proxy is on the
  helper's path. Its runner group is limited to selected workflows, this file at `refs/heads/main` only, so a branch's
  workflow cannot target it, and its runners are registered with `--ephemeral`.
- **Credentials.** Cloud access only by OIDC from a protected environment, to a role whose trust policy names
  that environment exactly (`repo:relay-example/relay:environment:<name>`). No cloud key is stored as a secret.
  Where a model provider accepts only API keys, the key is held by the protected `eval` environment, scoped to
  evaluation, spend-limited and rotated every 30 days (owner aisha.r). The `eval` environment has a required
  reviewer, because the triage gate runs pull-request code: without one, any branch, an agent's included, could
  read the key. The helper's GitHub App private key is the other long-lived secret near the pipeline: a secret of
  the protected `spec-to-pr` environment, readable only by that job (rotation owner sam.o).
- **Tokens.** Every new workflow sets `permissions: {}` at the top (the older `ci.yml` and
  `release.yml` grant only `contents: read`), and each job asks for the least it needs.
  `id-token: write` appears only in jobs bound to a protected environment, and checkout never persists
  credentials.
- **Tags.** A `v*` tag must name a commit on main; the build job fails otherwise. The gate-results attestation
  is only as trustworthy as the `pipeline.yml` at the tag, so that file must be one that main's review passed.
- **Gate inputs.** `docs/slo/` and every tool a gate or deploy step runs (`tools/`) are pipeline paths and gate
  configuration: lowering an SLO target would loosen the canary as surely as editing it.
- **Actions.** Pinned to full commit SHAs (SC007, ADR-028). Container images by digest.
- **Triggers.** No untrusted trigger anywhere (`pull_request_target`, `issue_comment`, `issues`,
  `workflow_run`); `workflow_dispatch` only, for write-access users, with inputs passed through `env`.
- **Pipeline changes.** `governance/pipeline-guard.json` lists the pipeline paths, `evals/` included. The
  `pipeline-guard` check enforces PG001-PG004: a pull request that changes a pipeline path changes nothing
  else; it needs two approvals by people after the last push, one from `@relay/platform-leads`, never the
  author, an agent or the person who asked the agent; any gate change (GD001-GD010, which include any change to
  a required job's commands and any change to gate configuration) also needs `@relay/security` and a reason
  naming a ticket. A check defined in the repository it guards can be switched off by the pull request it
  judges, so the guard runs from the platform team's repository at a pinned commit, required by an organization
  ruleset (`governance/required-workflows.json`); it reads its policy from the base branch and team membership
  from the platform, and fails if it cannot. Main requires the merge queue, so the guard runs again after
  approvals exist. Branch protection still asks for one approval on every pull request; the second approval for
  pipeline paths exists only in the guard, which is why the guard must not be removable.
- **Agents.** An agent may draft a pipeline change. It is reviewed like any other pipeline change, and the
  person who asked for it cannot be one of the two approvers.

## Consequences

- A pipeline fix now travels in its own pull request, which is slower in the moment and is the point.
- Hosted runners cannot reach private resources directly; the production job reaches AWS through OIDC and
  public APIs only. That is acceptable for ECS deployments and would need revisiting for a private registry.
- The guard's code lives outside Relay; changing the ruleset or the platform repository is a platform-lead and
  security change with its own review. The gate diff names common weakenings; GD009 and GD010 make every other
  change to a required job's commands or to gate configuration a security review.

## Rejected alternatives

### Option B — Self-hosted runners inside Relay's VPC, with stored deploy keys
Rejected because: a long-lived runner keeps state between jobs, and a stored key can be copied by any step that can read it, which is the theft OIDC removes.
Revisit if: a build needs private network access that no hosted runner can get, and then only with ephemeral runners that serve one job.

### Option C — CODEOWNERS alone for pipeline files
Rejected because: one approval satisfies every owning team the reviewer belongs to, so a pipeline line in a mixed pull request gets no review of its own.
Revisit if: the platform adds per-path approval requirements that do the guard's job.

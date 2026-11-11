# Runbook — release Relay through the pipeline

Owner: sam.o. Applies from 2027-05-04, when `RELAY_PIPELINE_MODE` became `deliver` (ADR-044). Until then the
15:00 UTC deploy train was the release path and the pipeline ran verify-only beside it.

## A normal release

1. A maintainer tags `vX.Y.Z` on a commit already on main; the build job refuses any other (only `v<digit>` tags
   start the pipeline). `.github/workflows/pipeline.yml`
   builds the image once and runs the four gates: test, eval (people's labels for judge-injection items, bound to
   the answers they judged; ADR-048), adversarial (the coverage gate) and scan (the three scanners and an image
   scan; every report required). Any failure stops the release; fix forward in a new pull request and tag again.
2. `release.yml` pushes the image, signs it and attaches the SBOM, AI-BOM, provenance and a gate-results
   attestation. The `admit` job records admission under `deploy/admission/policy.json`.
3. Open a pull request that sets `deploy/gitops/production.json` to the new release and digests, and nothing else.
   It is a pipeline path: two people approve it after the last push, one a platform lead (pipeline-guard).
4. Its merge runs `.github/workflows/deploy.yml`. The `production` environment asks one maintainer, not the
   person who triggered it, to approve. The job admits every image again, then rolls out by
   `deploy/rollout/canary.json`: 5%, 25%, 50%, 100%, 15 minutes each.
5. The rollout rolls back by itself on three judged minutes in a row with the canary burning at 14.4 or more on
   SLO-API-AVAIL or SLO-API-LATENCY and worse than the stable version. If both versions burn and the canary is no
   more than twice as bad, it holds and pages: usually a shared problem, not the release. Sixty held minutes in a
   step roll it back.
6. Record the release, digests, admission output and the rollout's decisions in the release ticket.

## Rolling back

A rollback is a pull request setting the desired state to an earlier release, with the same two approvals.
Admission checks it again: a release on `revoked_releases` (one later found vulnerable) cannot be rolled back to,
nor can one built before 2027-03-22, which has no gate-results attestation.

After an automatic canary rollback, production runs the previous release while `production.json` still names the
new one. The reconciler records the rollback instead of paging drift; the person who tagged the release opens the
revert of `production.json` the same day.

## An AI feature misbehaves

From the wiring planned for 2027-05-31 (ADR-047): trip the feature's kill switch
(`relay.release.flags.KillStore.trip`); the automation trips it itself when the feature's cohort is clearly worse
on SLO-TRIAGE-QUALITY or SLO-TRIAGE-SAFETY. The release stays. A person restores it with a reason that names a
ticket or an incident (`RLY-n: …` or `INC-n: …`). In 4.29.0 the service and worker do not yet read the flags, so
until then turn a feature off by a flags release.

## "Just this once"

There is no manual production deploy. An emergency fix is a release: tag it and let the pipeline run, with the
desired-state pull request's two approvals; that is the emergency path. Break-glass access (Chapter 14) exists
for the cloud account, not for deployments, and anything it changes shows up as drift (ADR-046).

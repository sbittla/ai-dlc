# Runbook — deploy a Relay release to non-production

Owner: sam.o. Runs from the protected `nonprod` CI environment (ADR-012), after the release workflow has
signed the images (ADR-030). Order matters: nothing starts that has not been verified, and nothing starts before
the schema is ready (ADR-031).

1. **Verify the images.** For each of `image_digest` and `proxy_image_digest` in the plan:

       cosign verify "$REGISTRY/relay@$DIGEST" \
         --certificate-identity "https://github.com/relay-example/relay/.github/workflows/release.yml@refs/tags/v$VERSION" \
         --certificate-oidc-issuer https://token.actions.githubusercontent.com

   Then verify the SBOM and AI-BOM attestations the same way (`cosign verify-attestation --type cyclonedx …`).
   Any failure stops the deployment. Never verify with a looser identity pattern than the exact tag.
2. **Plan and apply** the reviewed plan, with the desired counts unchanged.
3. **Migrate.** Run the one-off task `relay-nonprod-migrate` (`aws ecs run-task`) in the app subnets and wait
   for it to stop. Continue only if its exit code is 0. It logs in as `relay_migrator`.
4. **Grant.** Apply the table section of `infra/db/roles.sql` as the master user, so grants cover any table the
   migration created.
5. **Update the services** (`aws ecs update-service --force-new-deployment`) for the service and the worker.
6. **Record** the release version, both digests, the migration's output line and the verification output.

Until the PostgreSQL store adapter exists (ADR-014), steps 3 and 5 refuse to start by design, and the service
and worker desired counts are zero (`nonprod.tfvars`).

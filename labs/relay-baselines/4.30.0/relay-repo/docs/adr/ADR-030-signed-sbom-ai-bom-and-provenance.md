# ADR-030 — A signed SBOM, AI-BOM and build provenance for every release, verified before deployment

Status: accepted
Date: 2027-01-21
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), tomas.b (owner of the triage prompt and dataset), priya.n (engineering)
Links: ESC-N01, ESC-N03, CON-2
Related: ADR-015, ADR-020, ADR-028, ADR-029; Chapter 7 (triage-gate-v1)
Revisit when: the deployment platform verifies signatures natively at admission; or Relay loads a model file
itself; or CycloneDX or SPDX adds first-class component types for prompts and agents. Review by 2028-01-21 in
any case.
Supersedes: none.

## Context

After the incident behind ADR-028 the team could not answer, from records, which packages, images, prompts and
models a given release depended on, or prove that the image running was the one CI built. Customers' security
reviews ask both questions, and Chapter 7's evaluation gates mean the prompt and dataset versions are part of
what was approved.

## Options considered

### Option A — CycloneDX SBOM and AI-BOM generated from the repository's records, signed with Sigstore's keyless flow from the release workflow, plus build provenance; the deployment verifies identity and digest first

### Option B — An SBOM only, signed with a long-lived key held in CI

### Option C — No signing; rely on the registry's immutable tags

## Decision

Option A.

- `tools/sbom.py` writes `sbom.cdx.json` (Relay, each locked package with hash and source, the base image by
  digest) and `aibom.cdx.json` (models, prompts, datasets, evaluation gates, tool servers and every registered
  agent). Both are CycloneDX 1.6 and deterministic. A scan of the built image is attached alongside for the base
  image's own packages.
- Only maintainers may create or move `v*` tags (a tag ruleset in the platform's settings), and only those
  tags may deploy to the protected `release` environment. The release workflow, on such a tag, signs the image by digest and
  attaches both BOMs as signed attestations, using its own OIDC identity (no stored key), and records build
  provenance.
- `infra/runbooks/deploy.md` verifies, before anything runs: the signature's certificate identity is exactly
  the release workflow at a version tag, the issuer is GitHub's, the transparency-log entry exists, and the
  digest equals `image_digest` in the plan.
- A model file Relay loads must be safetensors, never pickle (`allowed_model_file_formats`). Relay 4.25.0 loads
  none; its triage model is hosted.

## Consequences

- An image built anywhere else, or signed by any other workflow, a branch or a fork, fails verification.
- The provenance shows where and from what the image was built; it does not show the code is safe. ADR-029's
  gates do that part.
- The BOMs are only as complete as `supply-chain/` and `governance/agents.json`; the supply-chain check and the
  registry tests keep those current.
- In this snapshot the workflow is illustrative and the digests are lab stand-ins. Lab 13.1 checks simulated
  signed bundles with the same rules.

## Rejected alternatives

### Option B — An SBOM only, signed with a long-lived key held in CI
Rejected because: a long-lived signing key is a credential worth stealing, as Chapter 14 found for tokens, and an SBOM without the models, prompts and agents misses what the triage approval depended on.
Revisit if: the organization runs its own signing service with keys in hardware.

### Option C — No signing; rely on the registry's immutable tags
Rejected because: immutability says a tag will not move, not who pushed it; anyone with push rights to the repository's registry could publish an image under a new tag.
Revisit if: never on its own; signing is cheap once the workflow exists.

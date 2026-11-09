# ADR-028 — Dependencies only from Relay's mirror, locked by hash; images, actions and tool servers pinned by digest

Status: accepted
Date: 2027-01-19
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N03, CON-1, CON-2
Related: ADR-007 (AR5), ADR-013, ADR-015, ADR-020, ADR-029, ADR-030; Chapter 3 (waiver WS023)
Revisit when: the mirror cannot serve a project the team needs within a working day; or the package index
offers signed provenance that pip verifies by default; or Relay adopts a second language. Review by 2028-01-19
in any case.
Dependency: pyjwt, cryptography, cffi, pycparser (admitted to the mirror for the token verifier; not imported by
`src/` until its own change); gunicorn and packaging (image, ADR-015); pytest and its dependencies (tests only)
Supersedes: none.

## Context

On Thursday 14 January 2027 a background coding session, prototyping the platform-token verifier that ADR-020
left open, installed a package whose name it had invented (composite; Lab 13.1, `report incident`). An attacker
had registered that name on the public index six weeks earlier. The package shipped only a source distribution,
so pip ran its setup code during the install, and that code sent the session's environment to a repository the
attacker controlled, through `api.github.com`, which the egress allowlist allows.

The sandbox could reach `pypi.org` because ADR-013 allowed it. Nothing checked a package name before pip
fetched it. The lock file pinned versions but not hashes, the base images were pinned by tag (waiver WS023,
expiring 2027-01-31) and the workflow actions by tag.

## Options considered

### Option A — A private mirror that serves only admitted projects; lock files with hashes, wheels only; every image, action and tool server pinned by digest or commit

### Option B — Keep the public index, and add a scanner (SCA) and a name-reputation check before install

### Option C — Vendor every dependency's source into the repository

## Decision

Option A.

- **The mirror** (`https://pypi-mirror.relay.example/simple/`) serves only projects listed in
  `supply-chain/mirror.json`, each admitted by an accepted ADR and a dependency review, with the reviewer and
  date. Names under the `relay-` prefix are internal and are never resolved from any public index. A new
  release of an admitted project is served only after a seven-day quarantine, unless aisha.r releases a security
  fix early. Chapter 1's dependency bot proposes only versions the mirror serves, and its automatic merge stays
  limited to patch updates of admitted projects whose checks pass.
- **Lock files** (`deploy/requirements.txt`, `requirements-dev.txt`) name the mirror as the only index, and set
  `--only-binary :all:` and `--require-hashes`. Every requirement is pinned with `==` and a sha256 hash, and the
  hash must equal the admitted file's.
- **The egress allowlist** replaces `pypi.org` and `files.pythonhosted.org` with the mirror.
- **Images** are pinned by digest everywhere: the dev container, both Containerfiles and the task definitions.
  This closes waiver WS023. Relay's own images are signed and verified (ADR-030). For third-party base images the
  publisher's signature or attestation is checked where one is offered; otherwise the digest, the image scan and
  `supply-chain/images.json`'s review are the controls.
- **Actions** in workflows are pinned to full commit SHAs. **MCP servers** in `.mcp.json` must match a reviewed
  entry in `supply-chain/ai-components.json`: the same launch command and arguments, a recorded source hash and
  a reviewer. The check compares the launch with the record; it does not hash the server's code, which is
  resolved from the import path at launch, so a launch-time hash check is still to be built.
- **pip's defaults** in the dev container and the agent sandbox are the mirror, wheels only and hashes
  required (`PIP_INDEX_URL`, `PIP_ONLY_BINARY=:all:`, `PIP_REQUIRE_HASHES=1`). `github.com` and
  `codeload.github.com` stay on the egress allowlist for git, so without these an ad hoc `pip install
  git+https://…` would fetch and build source from anywhere on GitHub.
- **Versions:** the mirror serves every release of an admitted project once its quarantine has passed. Relay's
  lock files are pinned further, to the one reviewed version per project in `mirror.json` (SC004); a different
  version is a reviewed change to both files.
- `tools/supplychain.py` (SC001–SC010) checks all of this as the `supply-chain` required status check and as a
  pre-commit hook. Its dependency rules are SC001–SC004; the near-miss and internal-name rules of Lab 13.1's
  teaching gate (DEP002, DEP003) are not in it.

**Dependency review of the token verifier's libraries.** PyJWT 2.10.1 with `cryptography` 44.0.1 (and its
`cffi` and `pycparser`) is admitted to the mirror for ADR-020's verifier of GitHub OIDC tokens (RS256 against
GitHub's published keys). The review checked: maintainers and release history; that both are published from CI
with the index's trusted publishing; that wheels exist for Relay's platforms; the open advisories for the
pinned versions (none at review); licences (MIT; Apache-2.0 or BSD-3-Clause); and the call surface the verifier
needs. Conditions: the verifier passes an explicit algorithm list (`["RS256"]`), the audience and the issuer on
every call; it never accepts `none` or an HMAC algorithm for a public key; and key sets are fetched only from
GitHub's documented JWKS address through the proxy. Building the verifier, and changing `dependencies = []`, is
its own change with its own ADR amendment.

**gunicorn review (ADR-015).** gunicorn 23.0.0 and its one dependency, packaging, stay. The review found no open
advisory for 23.0.0 at review, checked that the image runs it as an unprivileged user on a read-only root
filesystem behind the internal load balancer, and found nothing under `src/` that imports it.

## Consequences

- No package can enter a build through the lock files unless a person admitted its project, and pip's
  defaults refuse source and unhashed installs in the dev container and the sandbox. A hallucinated or
  typosquatted name fails at the mirror and at the check, not after its code ran. What remains: the GitHub
  hosts agents need still serve source archives, so a session can still clone and read unreviewed code, and a
  person overriding pip's defaults can still install it.
- Wheels only means no package's setup code runs at install time. It does not make a package safe: its code
  runs when imported, and a `.pth` file in a wheel runs when Python starts. Review and scanning remain.
- Hashes stop a changed file. They do not stop a malicious version published by the real maintainer, which the
  mirror would admit only when someone updates the lock; that update is a reviewed change.
- The Debian packages in the egress-proxy image are verified by apt's signed archive but pinned by version
  range, not hash. The image scan covers them.
- The hashes and digests in this snapshot are lab stand-ins in the right form, labelled in each file.

## Rejected alternatives

### Option B — Keep the public index, and add a scanner (SCA) and a name-reputation check before install
Rejected because: a scanner finds known vulnerabilities in known packages; a package registered last month by an attacker has no advisory, and reputation heuristics are evaded by publishing early and padding a release history, as the incident's package did.
Revisit if: the index offers verified publisher identity and provenance that pip enforces for every install.

### Option C — Vendor every dependency's source into the repository
Rejected because: it makes every update a large diff nobody reads, and loses the index's hashes and advisories, for a dependency list that is short enough to admit one project at a time.
Revisit if: the mirror becomes unavailable for builds that must be reproducible offline.

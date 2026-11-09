# Chapter 13 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch13/L13.1-secure-agent-loop/solution/secloop/` and `labs/ch13/L13.2-poisoned-instructions-ci-injection/solution/poisonlab/`, with modified copies of the gate policy and of the hardened workflow's configuration. They are locked by each lab's `tests/test_answers.py`. The data is generated and labelled, and the scanner results and attack outcomes follow from the generator's configuration.

## Recall

**1. What sam.o noticed, and what acts on it.**

| Property of `jwt-oidc-verify` | What acts on it in 4.25.0 |
| --- | --- |
| First published six weeks before the install (2 December 2026) | The mirror: the project is not admitted (DEP001), and a new release of an admitted project waits seven days |
| No source repository | The dependency review (template question on maintainers and source); DEP001's message reports it |
| Source distribution only, no wheels | `--only-binary :all:` in the lock files and the Containerfile; the mirror serves only reviewed wheels |

Strong answers add that the network now acts first: the proxy no longer reaches the public index, so the install fails before any of these checks matter. Full marks need three properties with a control each.

**2. SCA and slopsquatting.** SCA compares components with databases of known vulnerabilities. A package registered last month by an attacker has no advisory, so SCA reports nothing; in Lab 13.1 Trivy blocks none of the 20 hallucinated, typosquatted or confused dependencies. The dependency gate blocks all 20, because it checks where a package comes from, not whether it is known to be bad. Full marks need both halves.

**3. `--only-binary :all:`.** It refuses source distributions, so pip never builds a package on the installing machine and no build script runs during install (the incident's channel). It does not prevent code from running when the package is imported, `.pth` files in a wheel running at interpreter start, or a malicious wheel from a real maintainer. Full marks name at least one thing it does not prevent.

**4. RC-4 and RC-5.** A valid signature by the release workflow at the right tag proves who produced the bundle and that it was not changed afterwards. It does not prove the bundle is complete or acceptable. RC-4 is refused by REL007 (the AI-BOM omits `prompt:triage-v3.1`) and REL008 (a pickled model); RC-5 by REL006 (the SBOM omits `pkg:pypi/packaging@25.0`). Those checks compare the BOMs with Relay's own records, which is why the records have code owners.

## Apply

**5. Blocking threshold 8.0.** The gate then catches 61 of 100 seeded changes (59 before commit), against 83 (71) at 7.0, and blocks 1 clean change instead of 2. The losses: weak cryptography 7 → 0 (its rule is 7.4), path traversal 4 → 0 (7.5), vulnerable dependencies 8 → 0 (their advisories are 7.4 and 7.5), infrastructure 4 → 2 (7.0 and 7.1 drop), and the one secret only Semgrep found (7.5). Secrets and dependency findings are unaffected, since they always block.

Recommendation: do not make the change. It removes one false alarm and 22 catches. If the ETag false alarm is the problem, a reviewed suppression or a narrower rule (excluding `usedforsecurity=False`) fixes it without lowering the gate. Full marks need the numbers and a recommendation that follows from them.

**6. Dependency gate in CI only.** The totals do not change (83 caught), but only 51 are caught before commit instead of 71: the 20 dependency changes move to CI. In the incident that would not have mattered either way, because the damage happened at install, 17 minutes before the agent opened its pull request, and no commit-time gate runs at install. What stops the install is the network and the mirror: the proxy allowlist without the public index, and pip configured to use only the mirror with hashes required. Full marks need the 71 → 51 shift and the install-versus-commit point.

**7. Removing controls from version 2.** Without the author gate and without hidden-character stripping, two attacks succeed: C10 and C11, both a misleading reply. Outsiders' attacks still fail, because the agent has no shell, no push and no secret, and the comment never reaches a script. C13 and C14, the code leak and the OIDC-token theft, fail for the same reason: the agent has no network tool. Removing the link filter as well adds C09, a reply with an attacker's link: three succeed.

The sequence shows defence in depth working as designed. Each control covers a different path, and removing one or two raises the count only slightly because the others still hold. The remaining attacks are all about what the agent says, which is why a person must read replies that others act on. Full marks need the lists and that interpretation.

## Design

**8. A dependency-update agent.** Marking notes; a strong answer covers:

- **Identity and permissions:** its own registered agent identity (Chapter 14), a GitHub App token for one repository with contents and pull-requests write on its own branches only, never merge rights; no workflow permission; no secrets.
- **Mirror rules:** it may propose only versions the mirror serves; new releases wait seven days; it cannot admit a project, and a change to `supply-chain/mirror.json` needs `@relay/security`.
- **Gates:** the same pre-commit and CI gates as any agent, plus a diff of the package's file list and install hooks between versions, and SCA on the new version.
- **Scope:** it changes only lock files, one project per pull request, with the hash from the mirror; any other file fails re-verification.
- **Automatic merge:** only patch updates of admitted projects with every check passing, as Chapter 1's bot does, logged and sampled weekly, with a kill switch.
- **A compromised maintainer:** the quarantine gives time for reports; the diff of install hooks and new network calls flags the common forms; the SBOM per release finds every affected build if one gets through; rollback is a revert of one lock-file line.

Strong answers say what remains: a patient attacker who waits out the quarantine with a small, plausible change.

**9. AI-BOM for a self-hosted model.** Marking notes; a strong answer covers:

- A `machine-learning-model` component with the weights' sha256, format `safetensors` (REL008 refuses others), source repository and exact revision, licence, and owner.
- The tokenizer and configuration files as their own hashed components, since they also change behaviour.
- The evaluation that approved it: dataset name, version and hash, the gate (Chapter 7) and its result, linked from the model's entry.
- The serving image by digest, in the SBOM, signed with the AI-BOM.
- Release checks: identity and digest as for any image; the weights' hash equal to the evaluated one; a new revision deployable only after the same evaluation gate passes on it, recorded as a new AI-BOM entry.

## Marking scale

Recall 4 × 2 points, Apply 3 × 4 points, Design 2 × 5 points (30 in all). Answers that quote a lab number must match the lab's output.

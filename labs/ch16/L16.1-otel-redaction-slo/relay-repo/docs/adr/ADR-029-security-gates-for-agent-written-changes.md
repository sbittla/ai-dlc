# ADR-029 — Security gates in the agent loop, pre-commit and CI, with fixes re-verified

Status: accepted
Date: 2027-01-19
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N03, ESC-N07, CON-2
Related: ADR-028, ADR-020; Chapter 9 (review checklist, item 14); Chapter 3 (secret scanning)
Revisit when: a gate's false alarms exceed one confirmed alarm per rule per month; or a scanner's catch rate on
Lab 13.1's seeded set falls; or a class of weakness escapes to review twice in a quarter. Review by 2028-01-19 in
any case.
Supersedes: none.

## Context

Relay's agents write most of its changes. Until 4.25.0 the only automated security check on them was the
workspace audit's secret patterns. Chapter 9's review checklist names the weaknesses models repeat, such as
string-built SQL, missing authorization, secrets in code and unsafe deserialization, but a reviewer reading at
agent speed misses them. The incident behind ADR-028 also showed that no gate looked at dependencies at all.

## Options considered

### Option A — Three scanners plus the dependency gate, run before every commit the agent makes and again in CI, under one policy with reviewed suppressions; every automated fix re-verified

### Option B — Scanners in CI only

### Option C — An AI reviewer instead of rule-based scanners

## Decision

Option A, under policy `relay-security-gates-v1` (`security/gates.json`).

- **Pre-commit and the agent loop:** gitleaks on the staged change, Semgrep with Relay's rules
  (`security/semgrep.yml`) and the dependency gate. The agent may not commit until they pass.
- **CI:** the same, plus Trivy for known-vulnerable dependencies, image packages and infrastructure
  misconfiguration, as the `security-gates` and `supply-chain` required status checks.
- **Blocking:** any secret, any dependency finding, and SAST or SCA findings with security-severity 7.0 or more.
  A missing scanner report fails the build (exit 2).
- **Suppressions** (`security/suppressions.json`) bind one rule to one fingerprint, need a reason, a reviewer
  who is a person on the policy's list and not the author, and expire within 90 days. Dependency findings
  cannot be suppressed.
- **Fixes**, whether by an agent or a person, are accepted only if the same scanners then find nothing for the
  change, the tests pass, no suppression marker was added, no protected path (tests, scanner configuration,
  workflows, supply-chain files) changed, and the fix stays within the change's own files.

## Consequences

- Scanners catch patterns, not intent. Lab 13.1's seeded set shows authorization flaws escaping almost every
  rule; they stay with tests per route and Chapter 9's review.
- A rescan alone would accept a fix that silences the scanner. The policy checks above are what refuse it.
- DAST needs a running deployment, which Relay's non-production environment does not yet carry; it belongs
  with the delivery pipeline.
- AI-assisted triage may explain a finding, propose a fix or propose a suppression. It never closes a
  finding, and only a listed person can approve a suppression.

## Rejected alternatives

### Option B — Scanners in CI only
Rejected because: an agent that learns of a finding only after it has pushed has already put a secret in the remote history, and a CI round trip per attempt slows the loop more than local checks do.
Revisit if: local scanners become too slow for the agent loop on Relay's repository.

### Option C — An AI reviewer instead of rule-based scanners
Rejected because: its findings vary between runs, it can be steered by text in the change it reviews, and it cannot be audited rule by rule. It may add explanations on top of the gates.
Revisit if: an evaluated AI reviewer beats the rules on the held-out seeded set with an interval, and resists the injection cases of Lab 13.2.

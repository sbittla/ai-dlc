# ADR-020 — One identity per agent, federated from its workload, with 15-minute scoped Relay tokens

Status: accepted
Date: 2026-12-21
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), tomas.b (owner of eval-harvester), priya.n (engineering)
Links: ADR-012, ADR-021, ADR-022, Chapter 3 (ephemeral credentials), Chapter 11 (workload identity)
Revisit when: Relay adopts an external authorization server; or an agent needs a token longer than 15 minutes;
or a verifier for platform tokens (GitHub OIDC, AWS) is chosen as a dependency. Review by 2027-12-21 in any case.
Supersedes: none.

## Context

From 23 November to 14 December 2026 an attacker used a Relay service token belonging to the evaluation
harvester (composite; Lab 14.1, `report incident`). The token had no expiry, was shared by two jobs, had no
recorded owner, could export all six support projects, and was kept in a repository configuration variable
rather than a secret, so the runner had no reason to mask it. A failing run printed it, raw and base64-encoded,
and a CI agent posted the log in a public issue. Nothing in
Relay's request log named the agent or a person, so the misuse looked like the harvester.

Lab 14.1's inventory of that day finds 27 problems across six credentials and break-glass access, three of
them credentials with no expiry and one (a shared bot account's token) able to approve and merge.

## Options considered

### Option A — A registry of agent identities; each agent proves its workload and exchanges that for a 15-minute Relay token with the scopes it asked for

### Option B — Keep service tokens, but rotate them every 30 days and store them in Secrets Manager

### Option C — Give agents the identity of the person who runs them (personal tokens or delegated sessions)

## Decision

Option A. `governance/agents.json` registers every non-human identity that calls Relay: an id, an accountable
person, the workload it runs as (issuer and exact subject), its scopes, its delegation rule and any tool limits.
At run time an agent presents its platform's proof (a GitHub Actions OIDC token for CI jobs; a signed
`sts:GetCallerIdentity` request for ECS tasks) and receives a Relay token that lasts at most 900 seconds and
carries only the scopes requested, in the manner of OAuth 2.0 Token Exchange (RFC 8693). The proof must be
for Relay's audience and at most 300 seconds old. Every token names the agent, its owner and the person it acts
for; an agent that acts for someone must present that person's own short-lived proof as the subject token.

No agent may hold `workspace:admin`, `agents:manage`, `tokens:manage`, `audit:write`, `audit:delete` or
`break-glass:assume`; the registry refuses them. On GitHub, coding sessions use the `relay-agents` app's
one-hour installation tokens; the app is in no CODEOWNERS team and on no bypass list, and code-owner review and
last-push approval are required, so no agent's review can satisfy branch protection. CI agents assume their own
AWS roles (`infra/agents.tf`), pinned to one repository and one protected environment.

## Consequences

- A copied Relay token works for at most 15 minutes and only for its scopes; the harvester's token can no
  longer export anything. The kill switch (ADR-022) refuses every outstanding token at once.
- Each agent's actions are attributable in Relay's audit trail (ADR-021), and in CloudTrail by role.
- The platform-proof verifier is not in 4.23.0: verifying GitHub's RS256 tokens needs a cryptography library,
  which is a dependency under Chapter 6's rule and Chapter 13's review. Until then the token service is tested
  with verified claims written by hand, and the service does not yet call it (merge note in Lab 14.1).
- Tokens are signed with one HMAC key held by the service. Rotating that key invalidates every token, which is
  acceptable at a 15-minute lifetime; a key with the service's lifetime is a residual risk (owner aisha.r).
  Because the key is symmetric, verification stays inside the token service; no consumer verifies locally.
  Asymmetric signatures, so consumers can verify without being able to mint, are the later step.
- The subject token is only as strong as the person's sign-in and its lifetime: the session launcher holds it
  while the exchange happens, so it must be short-lived and issued for Relay's audience only.
- A Relay token is a bearer token: whoever holds it can use it until it expires or the switch trips. Binding
  tokens to the caller (DPoP, RFC 9449, or mutual TLS) is the stronger, later step.

## Rejected alternatives

### Option B — Keep service tokens, but rotate them every 30 days and store them in Secrets Manager
Rejected because: a rotated token is still long-lived between rotations, still shared by whoever reads the
secret, and still names no agent or person; the incident would have run for up to 30 days instead of 21.
Revisit if: a third-party integration cannot do token exchange; then one token per integration, 30-day expiry,
its own owner, read-only scopes and DR-001/DR-003 on it.

### Option C — Give agents the identity of the person who runs them
Rejected because: the agent then holds everything the person holds, including review and merge rights, and its
actions are indistinguishable from the person's. Delegation is recorded instead (`on_behalf_of`), with the
agent's own, narrower scopes.
Revisit if: never for autonomous or scheduled agents.

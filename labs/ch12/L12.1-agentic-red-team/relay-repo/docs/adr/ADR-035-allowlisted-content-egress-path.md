# ADR-035 — The allowlisted-content egress path: decrypt the content hosts at the proxy and allow only Relay's repository

Status: accepted
Date: 2027-02-10
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N07, CON-1
Related: ADR-013, ADR-028, ADR-032, ADR-034
Revisit when: an agent needs a second repository, GitHub changes the hosts its API or archives use, or a
broker replaces direct GitHub access for agents. Review by 2027-08-10 in any case.
Supersedes: none. Narrows the second gap ADR-013 recorded.

## Context

ADR-013 allowlisted five domains for background agent sessions, later four (ADR-028), and recorded two gaps
with sam.o as owner: DNS lookups through the VPC resolver, and content. Three of the four names,
`github.com`, `api.github.com` and `codeload.github.com`, serve anyone's repositories. Chapter 13's incident
sent a session's environment to an attacker's repository through `api.github.com`, and Chapter 12's red team
reproduced the same path with a steered agent that posts data as an issue in a repository its author owns.

The proxy sees only the name in each CONNECT, because it does not decrypt TLS. A domain allowlist cannot
tell `relay-example/relay` from any other repository on the same host.

## Options considered

### Option A — Decrypt tunnels to the content hosts at the proxy and allow only reviewed URL prefixes for Relay's repository

### Option B — Remove the content hosts from the allowlist and give agents a broker service that performs the few GitHub calls they need

### Option C — Keep the domain allowlist and rely on short-lived, repository-scoped tokens

## Decision

Option A, now. Option B is the direction for when the helper's GitHub calls are few enough to broker.

- `deploy/egress-proxy/content-hosts.txt` lists the three content hosts. Tunnels to them are bumped
  (decrypted) at the proxy; every other allowlisted name is spliced and checked by name only.
- Each decrypted request must match `content-urls.txt`: Relay's repository on each host and nothing else.
  Gists, search, GraphQL and every other owner's repository are refused, and the refusal is in the proxy's
  access log.
- The bump CA is generated per environment at deploy, mounted into the proxy task only, and trusted only by
  the sandbox image. Its key never enters an image.
- The image installs Debian's `squid-openssl`, the build with SslBump.

## Consequences

- A steered session can no longer post to an attacker's repository or gist through the allowlisted names,
  and can no longer fetch an attacker's file from them. Relay's own repository is still reachable, so
  content an outsider can write there (issue comments, if outsiders could comment) would still arrive.
- Decryption puts plaintext of the sessions' GitHub traffic, including their App tokens, in the proxy's
  memory. The proxy logs URLs, never headers, and its task has no other role.
- DNS lookups through the VPC resolver are still unfiltered (ADR-013's first gap). A steered agent with a
  network tool could still encode data in lookups; DNS Firewall is the planned control, and Relay's agents
  have no tool that resolves arbitrary names.
- Generating the CA and installing its certificate in the sandbox image are deployment changes, carried to
  the infrastructure's owners. Until they land, the configuration is reviewed but not deployed.

## Rejected alternatives

### Option B — Remove the content hosts from the allowlist and give agents a broker service that performs the few GitHub calls they need
Rejected because: for now, the coding sessions still clone and push over git, which a narrow broker does not yet cover, and a broker is a new service to run and secure.
Revisit if: the sessions' git traffic can move to a broker, or the helper's calls settle to a short list.

### Option C — Keep the domain allowlist and rely on short-lived, repository-scoped tokens
Rejected because: code that carries its own credentials can post to its author's repository, so the session's token scope does not decide where the data goes.
Revisit if: never as the only control on these hosts.

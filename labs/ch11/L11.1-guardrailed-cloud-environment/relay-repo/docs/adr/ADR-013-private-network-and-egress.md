# ADR-013 — Private networking, private model access and egress through one allowlisting proxy

Status: accepted
Date: 2026-11-30
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ADR-007, ADR-012, ESC-N07, CON-1
Revisit when: Relay's email or webhook delivery (trust boundaries TB3 and TB4) is built and needs internet egress from the worker; or agent sessions need a domain the proxy cannot serve; or interface endpoint charges exceed a third of the environment's fixed cost for two months running. Review by 2027-11-30 in any case.
Supersedes: none.

## Context

Chapter 3 left one risk open: the agent sandbox's network egress, owned by sam.o, so a steered agent could
send out what it can read. Chapter 6 left another: static fitness rules cannot see a network call made by a
subprocess (Lab 6.2's V09), so the control must be the environment's egress. The weekend lab's model server
was reachable from the internet on port 8000 with no authentication.

## Options considered

### Option A — No internet route for workloads; VPC endpoints for AWS services and the model API; one allowlisting proxy, reachable only from agent sandboxes

### Option B — A NAT gateway for every private subnet, with security groups allowing HTTPS anywhere

### Option C — A managed network firewall with a domain allowlist in front of a NAT gateway

## Decision

Option A. The app, data and sandbox subnets have no route beyond the VPC. The service and worker reach AWS
APIs through interface endpoints (Secrets Manager, CloudWatch Logs, ECR) and an S3 gateway endpoint. The
worker and agent sandboxes reach the model through a Bedrock runtime interface endpoint with private DNS and an
endpoint policy that admits two roles and one model. Background agent sessions run as Fargate tasks in
`sandbox_a`; their only way out is the egress proxy (`deploy/egress-proxy/`), which forwards HTTPS CONNECT to
five reviewed domains and refuses everything else. The proxy's HTTPS rule to 0.0.0.0/0 is the only such rule in
the configuration, and the policy checks allow exactly that rule. Nothing has a public IP address except the NAT
gateway, and the load balancer is internal, reachable only from the company VPN range.

At the price table's assumptions (Lab 11.1, `report cost`), the fixed cost of the environment is $221.90 a
month; network items are 56.7% of it, and the five interface endpoints alone 32.9%.

## Consequences

- Chapter 3's open-egress residual risk is closed for background agent sessions, which now run in the cloud
  sandbox. Agent sessions on a laptop's dev container keep open egress; the team's rule is that any task that
  reads untrusted content (tickets, issues, web pages) runs as a background session. sam.o keeps the narrowed
  residual risk, with a review date of 2027-01-31.
- DNS queries to the VPC resolver bypass security groups and the proxy. A steered agent could encode data in
  lookups of names it controls. This is a residual risk (owner sam.o); Route 53 Resolver DNS Firewall is the
  planned control.
- The proxy filters by name and does not decrypt TLS. An allowlisted domain that serves attacker-controlled
  content (a public repository, a package) is still reachable. Chapter 12 tests this path.
- Interface endpoints cost by the hour in every zone, whatever the traffic. This is the price of no internet
  route, and the cost estimate shows it on every plan.
- When TB3 and TB4 arrive, the worker's egress goes through the same proxy pattern with its own allowlist and
  its own ADR.

## Rejected alternatives

### Option B — A NAT gateway for every private subnet, with security groups allowing HTTPS anywhere
Rejected because: any process in the service or worker, including Lab 6.2's subprocess call, could reach any address on the internet, which leaves Chapter 3's residual risk open and makes ESC-N07 depend on code review alone.
Revisit if: never for subnets that hold Relay's data; acceptable for a throwaway sandbox with no data.

### Option C — A managed network firewall with a domain allowlist in front of a NAT gateway
Rejected because: one firewall endpoint at the price table's $0.395 an hour costs more than the whole proxy path, and filtering on the TLS server name admits a client that sends an allowlisted name to another address.
Revisit if: Relay needs egress filtering for many subnets or protocols other than HTTPS, or the proxy becomes an operational burden on the rota.

# Chapter 11 — Answers and Marking Notes

Arithmetic and outcomes in these answers were checked by running code from `labs/ch11/L11.1-guardrailed-cloud-environment/solution/cloudcheck/`: the cost estimate with `cost.estimate` and `cost.hours_to_threshold`, and the policy outcomes with `policy.run_policy` and `policy.gate_status` on modified copies of Relay's plan. All are locked by `labs/ch11/L11.1-guardrailed-cloud-environment/tests/test_answers.py`. Prices are the lab's dated assumptions (`data/prices/aws-us-east-1-2026-11.json`).

## Recall

**1. Shared responsibility for the model API.** Provider (any two): the infrastructure that hosts the model; the service's own availability and patching; handling of prompts and outputs inside the service under its published terms; isolation between customers. Relay (any three): which identities may call which model (task roles, the endpoint policy); the network path (the private endpoint, private DNS, no route out); what text is sent, by data class (Chapter 5's classification); what is done with the output (a suggestion only, D3); quotas and spend.

An SCP helps with the network path and the identities: Relay's denies model calls that do not arrive through a VPC endpoint, denies IAM users and keys, and limits regions. It does nothing about the content or the output. Strong answers say that the provider's terms are a residual risk Relay checks but cannot test (Chapter 6's threat model, owner aisha.r), and that the SCP's condition proves only that a call came through some VPC endpoint, not Relay's.

**2. Why `after` is not enough.** `after` leaves out every value unknown until apply, so an absent attribute could be unset or merely unknown; only `after_unknown` tells them apart. In S13 the rule's source address is unknown: a check reading `after` alone would see no 0.0.0.0/0 and pass it, while Relay's check reports "cannot check" and the gate exits 2.

`configuration` tells two further things apart. A security group's inline rules are unknown because the configuration sets none and the provider computes them from separate rule resources, so they are not judged. And it records references, such as the egress rule's `security_group_id` pointing to `aws_security_group.egress_proxy`, which is how the allowlist can be applied while the ID is unknown.

**3. SCPs against plan checks.** SCP only (any one): a GPU instance launched by a script or the console with an administrator session, as in the weekend lab; an IAM user or access key created outside the pipeline; a call in a region outside the list; switching off the audit trail. None of these pass through a plan.

Plan check only (any one): a missing budget, a missing public access block, a database without deletion protection or a standby, an OIDC trust without a pinned subject, an endpoint left with its default policy, or a missing tag on a resource type the SCPs do not cover. SCPs can deny an API call using its condition keys, but they cannot require something to exist or judge a combination of resources. Full marks need one of each, with the reason.

**4. Two budgets, and neither a guardrail.** The `env=nonprod` budget counts only resources carrying that tag, and only once the tag is activated for cost allocation; anything untagged, such as a hand-made resource, is invisible to it. The account budget counts everything. Neither is a guardrail because budgets alert after billing data arrives, which can lag by hours, and by default stop nothing. The guardrails are the SCPs and the plan checks, which refuse the resource.

## Apply

**5. A managed firewall instead of the proxy.** Remove the proxy service ($0.009875 an hour: 0.25 vCPU and 0.5 GB on Fargate ARM64) and add one firewall endpoint at $0.395 an hour.

| | Per hour | Per month (730 hours) |
| --- | ---: | ---: |
| Relay as built | $0.3040 | $221.90 |
| With a firewall endpoint instead of the proxy | **$0.6891** | **$503.04** |
| Increase | | **$281.14** |

The firewall would be **57.3%** of the fixed cost. The environment would exceed its $300 budget before any usage charges. Raising the budget to cover it would breach the policy's $500 ceiling for non-production budgets (POL009), so the change needs a policy decision, not only a bigger number. Strong answers add the firewall's per-gigabyte charge as a usage item, and note Table 11.2's bypass: filtering on the server name admits a client that sends an allowlisted name to another address.

**6. Late alerts.** At the lab's $34.68 an hour, with an 8-hour billing delay:

| Alert | Crossed after | Arrives after | Spent by then |
| --- | ---: | ---: | ---: |
| 50% of $300 | 4.3 h | 12.3 h (about 04:30 Saturday) | $427.46 |
| 80% | 6.9 h | 14.9 h | $517.46 |
| 100% | 8.7 h | 16.7 h (about 09:00 Saturday) | $577.46 |

Even a prompt alert arrives on a Friday evening or a Saturday morning, when nobody may act on it. Controls that would have stopped the spend sooner: the SCP that denies GPU instance types (no spend at all); the plan checks, had the script been a pull request; an `expires` tag with a scheduled teardown; or a budget action that stops instances. Full marks need the table and at least one preventive control.

**7. Two changes, one caught.**
- Opening the load balancer's HTTPS rule to 0.0.0.0/0: **POL001**, one finding, "ingress from 0.0.0.0/0 on tcp 443". Gate exit status **1**.
- Letting the worker invoke any foundation model: **no finding**; exit status **0**. The action is specific (`bedrock:InvokeModel`) and the resource is not `"*"`, so POL007 does not fire. The worker could now call any model, including one never evaluated (Chapter 7).

A rule that catches it: for every identity policy statement that allows a `bedrock:Invoke` action, each resource must equal one of the approved model ARNs listed in the policy file. A resource containing a wildcard fails. Strong answers add a seeded case for it, a control with the approved ARN, and say who maintains the list (the owner of Chapter 7's evaluation gate).

## Design

**8. Production.** Marking notes; look for these, each tied to an ADR:
- A separate production account in the workloads OU, with the same SCPs plus production ones (for example, no deletion of the database without the break-glass role).
- Public ingress for customers: an internet-facing load balancer in public subnets with a public certificate and a web application firewall, as a recorded exception to POL003 with its own threat model; everything behind it stays private.
- Data: Confidential data allowed only in production; backups kept 35 days (Relay's documented retention); deletion protection; restore and failover tests before go-live; a decision on a second region with recovery objectives stated.
- Cost: production budgets with alerts to the on-call rota; the endpoint and standby costs accepted in an ADR.
- Change: apply only from a protected production environment with two approvers; the apply role's service permissions narrowed (W-001 resolved) before production exists, and its IAM permissions kept bounded by the permissions boundary.
- Decommissioning replaces teardown, with data retention and deletion records.

A release check should include everything in this chapter's list plus the public-ingress threat model, a passed restore test, and the posture-management baseline. Answers that copy non-production unchanged, or open public ingress without an ADR, lose most marks.

**9. Closing a residual risk.** Either option earns full marks if it covers filter, bypass, cost, test and owner.
- *DNS egress:* Route 53 Resolver DNS Firewall on the VPC, with an allowlist domain list for the sandbox (the proxy's domains and the AWS service names) and a block-everything rule. Bypass: connecting to a hard-coded IP address, which the existing no-route design blocks; or DNS over HTTPS to an allowlisted host. Cost: per query and per domain list, small at non-production volume; verify the price. Seeded case: a sandbox lookup of an unlisted domain must be blocked, with an allowlisted lookup as the control. Owner: sam.o, with aisha.r reviewing.
- *Allowlisted content:* replace github.com and pypi.org with a pull-through mirror (a package repository proxy and a read-only mirror of approved repositories), so the sandbox can fetch but never push. Bypass: a malicious package that is already in the mirror, which needs Chapter 13's dependency controls. Cost: storage and requests. Seeded case: a push from the sandbox must fail. Owner: the platform team, with Chapter 13's reviewers.

Strong answers state what the control still cannot see.

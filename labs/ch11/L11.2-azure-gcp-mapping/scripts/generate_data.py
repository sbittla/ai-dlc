"""Write Lab 11.2's data/ folder. Deterministic: byte-identical on every platform.

    python scripts/generate_data.py

The mapping is the authors' reading of each provider's documentation in November 2026. Service
names change; every row is marked for verification before it is relied on. The prices are
ASSUMPTIONS: list prices as the authors read them on 2026-11-30, for one region per provider, with
no discounts. The lab teaches how pricing models differ and how to compare under stated
assumptions, not which provider is cheaper.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
DIMENSIONS = ["identity", "networking", "quotas", "pricing", "guardrails", "data"]


def row(concern, aws, azure, gcp, equivalence, *differences):
    return {"concern": concern, "aws": aws, "azure": azure, "gcp": gcp, "equivalence": equivalence,
            "differences": [{"dimension": d, "note": n} for d, n in differences], "verify": True}


MAPPING = {
    "version": "relay-cloud-mapping-2026.11",
    "as_of": "2026-11-30",
    "dimensions": DIMENSIONS,
    "equivalence_scale": {"close": "same job, similar controls; configuration differs",
                          "partial": "same job, but a control, scope or pricing model differs in a way that "
                                     "changes the design",
                          "different": "no direct equivalent; the design must change"},
    "rows": [
        row("Account boundary", "AWS account in an organizational unit", "Subscription under a management group",
            "Project under a folder", "partial",
            ("guardrails", "AWS SCPs attach to the organization root, OUs or accounts; Azure Policy is assigned to "
                           "management groups, subscriptions or resource groups; GCP organization policies to the "
                           "organization, folders or projects."),
            ("identity", "AWS IAM roles live in each account and cross-account access is explicit; Azure role "
                         "assignments and GCP IAM bindings are inherited down the hierarchy.")),
        row("Organization guardrails", "Service control policies (AWS Organizations)",
            "Azure Policy (deny, audit, modify effects) and deny assignments",
            "Organization Policy constraints and IAM deny policies", "partial",
            ("guardrails", "SCPs filter API actions by principal and never grant; Azure Policy evaluates resource "
                           "properties when resources are created or changed; GCP constraints restrict resource "
                           "configuration, and IAM deny policies deny permissions to principals.")),
        row("Workload identity", "ECS task IAM role", "User-assigned managed identity on the container app",
            "Service account attached to the Cloud Run service", "close",
            ("identity", "Each issues short-lived tokens to the running workload; permissions are role policies "
                         "(AWS), role assignments at a scope (Azure) or IAM bindings on resources (GCP).")),
        row("CI federation (no stored keys)", "IAM OIDC identity provider and a role trust policy",
            "Microsoft Entra workload identity federation (federated credential)",
            "Workload Identity Federation (pool and provider)", "close",
            ("identity", "All three exchange the CI provider's OIDC token; AWS conditions on the token's sub "
                         "claim, Azure matches a configured subject per federated credential, and GCP uses "
                         "attribute mappings and conditions.")),
        row("Network", "VPC: regional, one subnet per availability zone", "Virtual network: regional; subnets span "
            "the region's zones", "VPC network: global; subnets are regional and span zones", "partial",
            ("networking", "Two zones need two subnets on AWS and one on Azure or GCP; a GCP VPC can span regions "
                           "without peering.")),
        row("Stateful packet filter", "Security groups (allow rules only)",
            "Network security groups (allow and deny, by priority)",
            "VPC firewall rules and network firewall policies (allow and deny, by priority)", "partial",
            ("networking", "Security groups cannot deny; NSGs and GCP firewall rules can, and rule order "
                           "matters, so a review must read priorities as well as rules.")),
        row("Private access to the model API", "Amazon Bedrock runtime interface VPC endpoint with an endpoint "
            "policy", "Private endpoint for Azure OpenAI, public network access disabled",
            "Vertex AI through Private Google Access or a Private Service Connect endpoint, inside a VPC Service "
            "Controls perimeter", "partial",
            ("networking", "AWS and Azure place a private IP address for the service in your network; Private "
                           "Google Access reaches Google APIs from internal addresses without one."),
            ("guardrails", "VPC Service Controls draws a perimeter around projects that limits which networks and "
                           "identities can use an API; AWS combines endpoint policies with SCP conditions instead."),
            ("pricing", "AWS interface endpoints bill per zone per hour; an Azure private endpoint per endpoint "
                        "per hour; Private Google Access has no hourly charge."),
            ("quotas", "Model throughput limits are set per account, region and model (AWS), per subscription, "
                       "region and deployment (Azure), and per project, region and model (GCP).")),
        row("Private access to the database", "RDS in private subnets", "Flexible server with virtual network "
            "integration or a private endpoint", "Cloud SQL private IP through private services access", "close",
            ("networking", "Azure's virtual network integration needs a delegated subnet; Cloud SQL's private IP "
                           "uses a peered network that Google manages.")),
        row("Egress control", "No internet route; an allowlisting proxy behind a NAT gateway (or AWS Network "
            "Firewall)", "NAT gateway with Azure Firewall application rules, or a proxy",
            "Cloud NAT with Secure Web Proxy or Cloud NGFW FQDN rules, or a proxy", "close",
            ("pricing", "Managed name-based filtering is billed by the hour on all three; a small proxy container "
                        "avoids that charge and becomes the team's to run.")),
        row("Container runtime", "Amazon ECS on AWS Fargate", "Azure Container Apps (consumption plan)",
            "Cloud Run (instance-based billing)", "partial",
            ("pricing", "Fargate bills per vCPU and GB for each second a task runs; Container Apps per vCPU- and "
                        "GiB-second with a monthly free grant; Cloud Run per vCPU- and GiB-second at a lower rate "
                        "when billed per instance. The last two scale to zero without extra setup."),
            ("networking", "Container Apps and Cloud Run provide HTTPS ingress themselves; on ECS an internal "
                           "Application Load Balancer is a separate, hourly-billed resource.")),
        row("Managed PostgreSQL with a standby", "Amazon RDS for PostgreSQL, Multi-AZ",
            "Azure Database for PostgreSQL flexible server, zone-redundant high availability",
            "Cloud SQL for PostgreSQL, high availability (regional)", "partial",
            ("pricing", "A standby roughly doubles compute and storage on all three. Azure's burstable tier does "
                        "not offer high availability, so the smallest highly available server is larger."),
            ("data", "All three replicate synchronously to a standby in another zone and fail over automatically; "
                     "none protects against a bad write, which backups and point-in-time restore cover.")),
        row("Secrets", "AWS Secrets Manager", "Azure Key Vault secrets", "Secret Manager", "close",
            ("pricing", "AWS charges per secret per month; Key Vault per 10,000 operations; Secret Manager per "
                        "active secret version per month and per access.")),
        row("Customer-managed keys", "AWS KMS customer managed keys", "Azure Key Vault keys (or Managed HSM)",
            "Cloud KMS", "close",
            ("pricing", "AWS charges per key per month; Key Vault standard keys per operation; Cloud KMS per active "
                        "key version per month.")),
        row("Budgets and alerts", "AWS Budgets", "Cost Management budgets", "Cloud Billing budgets", "close",
            ("guardrails", "None stops spending by default. AWS budget actions can apply a policy or stop some "
                           "resources; Azure budgets can trigger action groups; GCP budgets publish to Pub/Sub, which "
                           "automation can act on.")),
        row("Posture management", "AWS Security Hub with AWS Config rules", "Microsoft Defender for Cloud (CSPM)",
            "Security Command Center", "close",
            ("guardrails", "Each finds drift in the live account that plan-time checks cannot see; the rule sets and "
                           "their names differ.")),
        row("Infrastructure as code provider", "hashicorp/aws", "hashicorp/azurerm (and azapi)", "hashicorp/google",
            "different",
            ("data", "Resource types, attribute names and defaults differ entirely; Lab 11.1's rules carry over, but "
                     "every check must be rewritten against the other provider's plan.")),
    ],
}

REQUIRED = [r["concern"] for r in MAPPING["rows"]]

# An agent's first draft of the mapping, unedited: the lab's checker should find its problems.
DRAFT = {
    "version": "agent-draft",
    "as_of": "2026-11-30",
    "dimensions": DIMENSIONS,
    "rows": [
        row("Account boundary", "AWS account", "Subscription", "Project", "close"),
        row("Organization guardrails", "Service control policies", "Azure Policy", "Organization Policy", "close"),
        row("Workload identity", "ECS task IAM role", "Managed identity", "", "close"),
        row("Private access to the model API", "Bedrock VPC endpoint", "Azure OpenAI private endpoint",
            "Vertex AI private endpoint", "partial"),
        row("Container runtime", "ECS on Fargate", "Azure Container Apps", "Cloud Run", "close",
            ("cost", "Serverless containers are cheaper.")),
        row("Container runtime", "ECS on Fargate", "Azure Kubernetes Service", "Google Kubernetes Engine", "close"),
    ],
}

WORKLOAD = {
    "name": "relay-nonprod",
    "source": "Lab 11.1, relay-repo/infra/ (Relay 4.21.0)",
    "hours_per_month": 730,
    "containers": [
        {"name": "service", "vcpu": 0.5, "gib": 1.0, "count": 2, "schedulable": True},
        {"name": "worker", "vcpu": 0.25, "gib": 0.5, "count": 1, "schedulable": False},
        {"name": "egress-proxy", "vcpu": 0.25, "gib": 0.5, "count": 1, "schedulable": False},
    ],
    "database": {"engine": "postgresql", "high_availability": True, "storage_gib": 20},
    "private_endpoints": {"services": 5, "zones": 2},
    "nat_gateways": 1,
    "public_ipv4": 1,
    "internal_load_balancer": True,
    "secrets": 1,
    "keys": 1,
    "not_compared": "Usage-based charges (data processed, requests, logs, storage growth, model tokens)",
}

STATUS = ("ASSUMPTIONS. On-demand list prices as the authors read them on the as-of date, one region, no "
          "discounts, credits or commitments. Verify every price before relying on a comparison.")

PRICES = {
    "aws": {
        "provider": "aws", "region": "us-east-1", "as_of": "2026-11-30", "status": STATUS,
        "containers": {"billing": "per_second", "service": "ECS on Fargate, ARM64",
                       "vcpu_second": 0.03238 / 3600, "gib_second": 0.00356 / 3600,
                       "note": "billed per second with a one-minute minimum; listed as $0.03238 per vCPU-hour "
                               "and $0.00356 per GB-hour"},
        "database": {"service": "RDS for PostgreSQL", "class": "db.t4g.small", "class_hour": 0.032,
                     "ha_factor": 2, "storage_gib_month": 0.115, "storage_ha_factor": 2,
                     "note": "Multi-AZ standby"},
        "private_endpoints": {"billing": "per_service_per_zone_hour", "rate": 0.01},
        "nat_gateway_hour": 0.045,
        "public_ipv4_hour": 0.005,
        "internal_load_balancer_hour": 0.0225,
        "secret_month": 0.40,
        "key_month": 1.00,
    },
    "azure": {
        "provider": "azure", "region": "East US", "as_of": "2026-11-30", "status": STATUS,
        "containers": {"billing": "per_second_with_grant", "service": "Container Apps, consumption, active rate",
                       "vcpu_second": 0.000024, "gib_second": 0.000003,
                       "free_vcpu_seconds": 180000, "free_gib_seconds": 360000},
        "database": {"service": "Database for PostgreSQL flexible server", "class": "General Purpose D2ds_v5",
                     "class_hour": 0.178, "ha_factor": 2, "storage_gib_month": 0.115, "storage_ha_factor": 2,
                     "note": "zone-redundant HA; burstable servers cannot use HA",
                     "without_ha": {"class": "Burstable B1ms", "class_hour": 0.0207}},
        "private_endpoints": {"billing": "per_service_hour", "rate": 0.01},
        "nat_gateway_hour": 0.045,
        "public_ipv4_hour": 0.005,
        "internal_load_balancer_hour": 0.0,
        "secret_month": 0.0,
        "key_month": 0.0,
    },
    "gcp": {
        "provider": "gcp", "region": "us-central1", "as_of": "2026-11-30", "status": STATUS,
        "containers": {"billing": "per_second", "service": "Cloud Run, instance-based billing",
                       "vcpu_second": 0.000018, "gib_second": 0.000002},
        "database": {"service": "Cloud SQL for PostgreSQL, Enterprise edition", "class": "1 vCPU, 3.75 GB",
                     "class_hour": 0.06755, "ha_factor": 2, "storage_gib_month": 0.17, "storage_ha_factor": 2,
                     "note": "regional HA"},
        "private_endpoints": {"billing": "none", "rate": 0.0},
        "nat_gateway_hour": 0.0014,
        "public_ipv4_hour": 0.005,
        "internal_load_balancer_hour": 0.0,
        "secret_month": 0.06,
        "key_month": 0.06,
    },
}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, indent=1) + "\n")


def main() -> None:
    write_json(DATA / "mapping.json", MAPPING)
    write_json(DATA / "mapping-draft.json", DRAFT)
    write_json(DATA / "required-concerns.json", {"concerns": REQUIRED})
    write_json(DATA / "workload.json", WORKLOAD)
    for name, table in PRICES.items():
        write_json(DATA / "prices" / f"{name}-2026-11.json", table)


if __name__ == "__main__":
    main()

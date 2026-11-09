# Organization guardrails (ADR-012): service control policies for the workloads OU
# that holds Relay's non-production account. This is a separate root module, planned
# and applied by the platform team from the management account; Relay's CI roles
# cannot change it. SCPs only restrict: they never grant a permission, they do not
# apply to the management account, and an OU or account can have at most five
# attached, including AWS's default FullAWSAccess policy.

terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

variable "nonprod_ou_id" {
  type        = string
  description = "The organizational unit for non-production workload accounts."
}

locals {
  scps = {
    "deny-regions"             = "Only us-east-1 and us-west-2, except global services"
    "deny-instance-types"      = "Small compute and database sizes only; no self-hosted model endpoints"
    "protect-baseline"         = "Audit trail stays on; no IAM users or access keys; no public snapshots"
    "private-models-and-tags"  = "Model calls only through a VPC endpoint; owner and cost-center tags on create"
  }
}

resource "aws_organizations_policy" "scp" {
  for_each    = local.scps
  name        = "relay-${each.key}"
  description = each.value
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${path.module}/scp-${each.key}.json")
}

resource "aws_organizations_policy_attachment" "nonprod" {
  for_each  = aws_organizations_policy.scp
  policy_id = each.value.id
  target_id = var.nonprod_ou_id
}

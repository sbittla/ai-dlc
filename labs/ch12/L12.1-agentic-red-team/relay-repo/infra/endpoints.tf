# Private access to AWS services (ADR-013). With no internet route, every AWS API the
# tasks call goes through an endpoint in the VPC. Interface endpoints are billed per
# zone per hour, so each one here is a line in the cost estimate.
#
# Every endpoint carries a policy. Without one, AWS applies a default that allows any
# principal, from any account, any action: a steered process could then use an endpoint
# with credentials an attacker supplies, or write to an attacker's bucket through the S3
# gateway. The policies below admit only principals of this account (and, where the
# service supports it, only resources of this account); the S3 gateway admits only reads
# of the bucket that holds ECR's image layers.

locals {
  interface_endpoints = {
    secretsmanager = "com.amazonaws.${var.region}.secretsmanager"
    logs           = "com.amazonaws.${var.region}.logs"
    ecr_api        = "com.amazonaws.${var.region}.ecr.api"
    ecr_dkr        = "com.amazonaws.${var.region}.ecr.dkr"
  }

  own_principals_only = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "ThisAccountsPrincipalsOnly"
      Effect    = "Allow"
      Principal = "*"
      Action    = "*"
      Resource  = "*"
      Condition = { StringEquals = { "aws:PrincipalAccount" = var.account_id } }
    }]
  })

  own_principals_and_resources = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "ThisAccountOnly"
      Effect    = "Allow"
      Principal = "*"
      Action    = "*"
      Resource  = "*"
      Condition = { StringEquals = { "aws:PrincipalAccount" = var.account_id, "aws:ResourceAccount" = var.account_id } }
    }]
  })
}

# The model API. Only two roles may use it, and only for the one approved model; the
# organization's guardrail denies model calls that do not arrive through a VPC endpoint.
# The role ARNs are written from the same names as the roles in iam.tf rather than as
# references, so the policy is known at plan time and the policy checks can read it.
resource "aws_vpc_endpoint" "bedrock_runtime" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ApprovedModelOnly"
      Effect = "Allow"
      Principal = {
        AWS = [
          "arn:aws:iam::${var.account_id}:role/${local.name}-worker",
          "arn:aws:iam::${var.account_id}:role/${local.name}-sandbox",
        ]
      }
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = [var.triage_model_arn]
    }]
  })
}

resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.secretsmanager
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  policy              = local.own_principals_and_resources
}

resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.logs
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  policy              = local.own_principals_and_resources
}

resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.ecr_api
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  policy              = local.own_principals_only
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.ecr_dkr
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  policy              = local.own_principals_only
}

# Image layers come from S3. A gateway endpoint has no hourly charge. Its policy admits
# reads of ECR's layer bucket for this region and nothing else, so no task, including an
# agent session, can write to another bucket through it.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.sandbox.id, aws_route_table.egress.id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EcrImageLayersOnly"
      Effect    = "Allow"
      Principal = "*"
      Action    = ["s3:GetObject"]
      Resource  = ["arn:aws:s3:::prod-${var.region}-starport-layer-bucket/*"]
    }]
  })
}

# Private access to AWS services (ADR-013). With no internet route, every AWS API the
# tasks call goes through an endpoint in the VPC. Interface endpoints are billed per
# zone per hour, so each one here is a line in the cost estimate.

locals {
  interface_endpoints = {
    secretsmanager = "com.amazonaws.${var.region}.secretsmanager"
    logs           = "com.amazonaws.${var.region}.logs"
    ecr_api        = "com.amazonaws.${var.region}.ecr.api"
    ecr_dkr        = "com.amazonaws.${var.region}.ecr.dkr"
  }
}

# The model API. Only two roles may use it, and only for the one approved model; the
# organization's guardrail denies model calls that do not arrive through a VPC endpoint.
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
}

resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.logs
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
}

resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.ecr_api
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = aws_vpc.main.id
  service_name        = local.interface_endpoints.ecr_dkr
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_group_ids  = [aws_security_group.endpoints.id]
}

# Image layers come from S3. A gateway endpoint has no hourly charge.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.egress.id]
}

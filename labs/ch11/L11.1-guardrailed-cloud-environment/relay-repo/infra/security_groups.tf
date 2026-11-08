# Security groups (ADR-013). Rules are separate resources, one per permitted flow, and
# every rule names its peer group rather than an address range wherever it can. The
# provider removes the allow-all egress rule AWS adds to a new group, so a group with
# no egress rule here can send nothing.
#
# The one rule to 0.0.0.0/0 is the egress proxy's HTTPS rule. The proxy forwards only
# to the domains in deploy/egress-proxy/allowlist.txt, and only the agent sandbox may
# reach it. The policy checks allow exactly this rule (data/policy.json in Lab 11.1).

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Internal load balancer"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "service" {
  name        = "${local.name}-service"
  description = "Relay HTTP service tasks"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "worker" {
  name        = "${local.name}-worker"
  description = "Relay triage worker tasks"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "tasks" {
  name        = "${local.name}-tasks"
  description = "Every ECS task: image pulls, logs and secrets through endpoints"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "endpoints" {
  name        = "${local.name}-endpoints"
  description = "Interface VPC endpoints"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "PostgreSQL"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "sandbox" {
  name        = "${local.name}-sandbox"
  description = "Background agent sessions"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "egress_proxy" {
  name        = "${local.name}-egress-proxy"
  description = "Allowlisting HTTPS proxy for agent sandboxes"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_vpn" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from the company VPN only"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = var.vpn_cidr
}

resource "aws_vpc_security_group_egress_rule" "alb_to_service" {
  security_group_id            = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  referenced_security_group_id = aws_security_group.service.id
}

resource "aws_vpc_security_group_ingress_rule" "service_from_alb" {
  security_group_id            = aws_security_group.service.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "service_to_db" {
  security_group_id            = aws_security_group.service.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.db.id
}

resource "aws_vpc_security_group_egress_rule" "worker_to_db" {
  security_group_id            = aws_security_group.worker.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.db.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_service" {
  security_group_id            = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.service.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_worker" {
  security_group_id            = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.worker.id
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_tasks" {
  security_group_id            = aws_security_group.endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.tasks.id
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_sandbox" {
  security_group_id            = aws_security_group.endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.sandbox.id
}

resource "aws_vpc_security_group_egress_rule" "tasks_to_endpoints" {
  security_group_id            = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.endpoints.id
}

resource "aws_vpc_security_group_egress_rule" "tasks_to_s3" {
  security_group_id = aws_security_group.tasks.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
}

# Agent sessions run with the sandbox group only, never the shared tasks group, so their
# paths are exactly these three: the proxy, the endpoints and the S3 gateway (image layers).
resource "aws_vpc_security_group_egress_rule" "sandbox_to_endpoints" {
  security_group_id            = aws_security_group.sandbox.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.endpoints.id
}

resource "aws_vpc_security_group_egress_rule" "sandbox_to_s3" {
  security_group_id = aws_security_group.sandbox.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
}

resource "aws_vpc_security_group_egress_rule" "sandbox_to_proxy" {
  security_group_id            = aws_security_group.sandbox.id
  ip_protocol                  = "tcp"
  from_port                    = 3128
  to_port                      = 3128
  referenced_security_group_id = aws_security_group.egress_proxy.id
}

resource "aws_vpc_security_group_ingress_rule" "proxy_from_sandbox" {
  security_group_id            = aws_security_group.egress_proxy.id
  ip_protocol                  = "tcp"
  from_port                    = 3128
  to_port                      = 3128
  referenced_security_group_id = aws_security_group.sandbox.id
}

resource "aws_vpc_security_group_egress_rule" "proxy_https_internet" {
  security_group_id = aws_security_group.egress_proxy.id
  description       = "Allowlisted exception: the proxy forwards to allowlisted domains only"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# Network (ADR-013). Two zones. Workloads, endpoints and the database have no route
# to the internet at all. Only the egress proxy's subnet routes to a NAT gateway, and
# only the agent sandbox may reach the proxy.
#
#   app_a, app_b         service, worker, internal load balancer, interface endpoints
#   data_a, data_b       the database
#   sandbox_a            background agent sessions (Chapter 3's sandbox, in the cloud)
#   egress_a             the egress proxy: the one subnet with a route out
#   public_a             the NAT gateway only; nothing else is placed here

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}

# The default security group allows traffic between its members. Nothing uses it,
# and this resource removes all of its rules.
resource "aws_default_security_group" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "app_a" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[0]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-app-a" }
}

resource "aws_subnet" "app_b" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[1]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 2)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-app-b" }
}

resource "aws_subnet" "data_a" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[0]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 11)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-data-a" }
}

resource "aws_subnet" "data_b" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[1]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 12)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-data-b" }
}

resource "aws_subnet" "sandbox_a" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[0]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 21)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-sandbox-a" }
}

resource "aws_subnet" "egress_a" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[0]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 31)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-egress-a" }
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[0]
  cidr_block              = cidrsubnet(var.vpc_cidr, 12, 656) # 10.40.41.0/28
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-public-a" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "egress" {
  allocation_id     = aws_eip.nat.id
  subnet_id         = aws_subnet.public_a.id
  connectivity_type = "public"
}

# No routes beyond the VPC itself: the app, data and sandbox subnets cannot reach the
# internet, whatever their security groups say.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "egress" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.egress.id
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "app_a" {
  subnet_id      = aws_subnet.app_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "app_b" {
  subnet_id      = aws_subnet.app_b.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "data_a" {
  subnet_id      = aws_subnet.data_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "data_b" {
  subnet_id      = aws_subnet.data_b.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "sandbox_a" {
  subnet_id      = aws_subnet.sandbox_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "egress_a" {
  subnet_id      = aws_subnet.egress_a.id
  route_table_id = aws_route_table.egress.id
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_flow_log" "main" {
  vpc_id               = aws_vpc.main.id
  traffic_type         = "ALL"
  log_destination_type = "s3"
  log_destination      = aws_s3_bucket.flow_logs.arn
}

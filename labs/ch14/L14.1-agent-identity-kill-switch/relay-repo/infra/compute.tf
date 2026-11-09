# Compute (ADR-015). One image, three long-running services on ECS Fargate, and an
# on-demand task definition for background agent sessions. No task gets a public IP,
# and ECS Exec is off: nobody opens a shell in a running task.

resource "aws_ecr_repository" "relay" {
  name                 = "relay"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.relay.arn
  }
}

resource "aws_ecr_repository" "egress_proxy" {
  name                 = "relay-egress-proxy"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.relay.arn
  }
}

resource "aws_cloudwatch_log_group" "service" {
  name              = "/relay/${var.env}/service"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.relay.arn
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/relay/${var.env}/worker"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.relay.arn
}

resource "aws_cloudwatch_log_group" "egress_proxy" {
  name              = "/relay/${var.env}/egress-proxy"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.relay.arn
}

resource "aws_cloudwatch_log_group" "sandbox" {
  name              = "/relay/${var.env}/sandbox"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.relay.arn
}

resource "aws_ecs_cluster" "relay" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  image       = "${aws_ecr_repository.relay.repository_url}:${var.image_tag}"
  proxy_image = "${aws_ecr_repository.egress_proxy.repository_url}:${var.image_tag}"

  hardening = {
    readonlyRootFilesystem = true
    user                   = "10001"
    linuxParameters        = { capabilities = { drop = ["ALL"] }, initProcessEnabled = true }
  }

  log = { for k, g in {
    service      = aws_cloudwatch_log_group.service.name
    worker       = aws_cloudwatch_log_group.worker.name
    egress_proxy = aws_cloudwatch_log_group.egress_proxy.name
    sandbox      = aws_cloudwatch_log_group.sandbox.name
    } : k => {
    logDriver = "awslogs"
    options   = { "awslogs-group" = g, "awslogs-region" = var.region, "awslogs-stream-prefix" = k }
  } }
}

resource "aws_ecs_task_definition" "service" {
  family                   = "${local.name}-service"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.service_task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([merge(local.hardening, {
    name         = "relay-service"
    image        = local.image
    essential    = true
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "RELAY_DB_HOST", value = aws_db_instance.relay.address },
      { name = "RELAY_DB_USER", value = "relay_service" },
      { name = "RELAY_DIRECTORY_FILE", value = "/run/relay/directory.json" },
    ]
    secrets          = [{ name = "RELAY_DIRECTORY_JSON", valueFrom = aws_secretsmanager_secret.directory.arn }]
    logConfiguration = local.log.service
  })])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([merge(local.hardening, {
    name       = "relay-worker"
    image      = local.image
    essential  = true
    entryPoint = ["python", "-m", "relay.worker"]
    environment = [
      { name = "RELAY_DB_HOST", value = aws_db_instance.relay.address },
      { name = "RELAY_DB_USER", value = "relay_worker" },
      { name = "RELAY_TRIAGE_MODEL", value = var.triage_model_arn },
    ]
    logConfiguration = local.log.worker
  })])
}

resource "aws_ecs_task_definition" "egress_proxy" {
  family                   = "${local.name}-egress-proxy"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([merge(local.hardening, {
    name             = "egress-proxy"
    image            = local.proxy_image
    essential        = true
    portMappings     = [{ containerPort = 3128, protocol = "tcp" }]
    logConfiguration = local.log.egress_proxy
  })])
}

# Background agent sessions (Chapter 3's sandbox) run as one-off tasks from this
# definition, in sandbox_a, with HTTPS_PROXY pointing at the egress proxy.
resource "aws_ecs_task_definition" "sandbox" {
  family                   = "${local.name}-sandbox"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.sandbox_task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([merge(local.hardening, {
    name      = "agent-sandbox"
    image     = local.image
    essential = true
    environment = [
      { name = "HTTPS_PROXY", value = "http://egress-proxy.${local.name}.internal:3128" },
      { name = "RELAY_ENV", value = "sandbox" },
    ]
    logConfiguration = local.log.sandbox
  })])
}

resource "aws_ecs_service" "service" {
  name                   = "${local.name}-service"
  cluster                = aws_ecs_cluster.relay.id
  task_definition        = aws_ecs_task_definition.service.arn
  desired_count          = var.service_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"
  network_configuration {
    subnets          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
    security_groups  = [aws_security_group.service.id, aws_security_group.tasks.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.service.arn
    container_name   = "relay-service"
    container_port   = 8080
  }
}

resource "aws_ecs_service" "worker" {
  name                   = "${local.name}-worker"
  cluster                = aws_ecs_cluster.relay.id
  task_definition        = aws_ecs_task_definition.worker.arn
  desired_count          = var.worker_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"
  network_configuration {
    subnets          = [aws_subnet.app_a.id, aws_subnet.app_b.id]
    security_groups  = [aws_security_group.worker.id, aws_security_group.tasks.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "egress_proxy" {
  name                   = "${local.name}-egress-proxy"
  cluster                = aws_ecs_cluster.relay.id
  task_definition        = aws_ecs_task_definition.egress_proxy.arn
  desired_count          = var.proxy_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"
  network_configuration {
    subnets          = [aws_subnet.egress_a.id]
    security_groups  = [aws_security_group.egress_proxy.id, aws_security_group.tasks.id]
    assign_public_ip = false
  }
  service_registries {
    registry_arn = aws_service_discovery_service.egress_proxy.arn
  }
}

# The sandbox finds the proxy by a private DNS name, egress-proxy.relay-nonprod.internal.
resource "aws_service_discovery_private_dns_namespace" "internal" {
  name = "${local.name}.internal"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "egress_proxy" {
  name = "egress-proxy"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal.id
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
}

resource "aws_lb" "internal" {
  name                       = "${local.name}-internal"
  internal                   = true
  load_balancer_type         = "application"
  drop_invalid_header_fields = true
  subnets                    = [aws_subnet.app_a.id, aws_subnet.app_b.id]
  security_groups            = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "service" {
  name        = "${local.name}-service"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id
  health_check {
    path    = "/healthz"
    matcher = "200"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service.arn
  }
}

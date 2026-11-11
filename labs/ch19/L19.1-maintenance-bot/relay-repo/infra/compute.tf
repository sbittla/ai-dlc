# Compute (ADR-015; wired in 4.25.0, ADR-031). One image, three long-running services on ECS
# Fargate, an on-demand task definition for background agent sessions, and a one-off migration
# task. No task gets a public IP, and ECS Exec is off: nobody opens a shell in a running task.
#
# From 4.25.0 every image is referenced by digest, never by tag (ADR-028): the digest is the
# one the release workflow signed, and infra/runbooks/deploy.md verifies its signature first.

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
  image       = "${aws_ecr_repository.relay.repository_url}@${var.image_digest}"
  proxy_image = "${aws_ecr_repository.egress_proxy.repository_url}@${var.proxy_image_digest}"

  # The directory secret reaches only this init container, which writes it to a task-local
  # volume and exits; the main container mounts that volume read-only (ADR-031).
  config_volume = "relay-config"
  write_config = merge(local.hardening, {
    name        = "write-config"
    image       = local.image
    essential   = false
    entryPoint  = ["python", "-c", "import os, pathlib; pathlib.Path('/run/relay/directory.json').write_text(os.environ['RELAY_DIRECTORY_JSON'], encoding='utf-8')"]
    secrets     = [{ name = "RELAY_DIRECTORY_JSON", valueFrom = aws_secretsmanager_secret.directory.arn }]
    mountPoints = [{ sourceVolume = "relay-config", containerPath = "/run/relay", readOnly = false }]
  })
  read_config = {
    dependsOn = [{ containerName = "write-config", condition = "SUCCESS" }]
    mountPoints = [
      { sourceVolume = "relay-config", containerPath = "/run/relay", readOnly = true },
      { sourceVolume = "relay-data", containerPath = "/var/lib/relay", readOnly = false },
    ]
  }

  # PLACEHOLDER until the PostgreSQL store adapter exists (ADR-014, ADR-031). Each task gets its own
  # writable task-local volume for the SQLite file, so the paths can be opened, but no two tasks share
  # a database. That is why the service and the migration refuse to start while RELAY_DB_HOST is set,
  # and why nonprod.tfvars keeps the service and worker at zero tasks. The worker has no such check.
  data_volume = "relay-data"
  db_path     = "/var/lib/relay/relay.db"

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
  volume {
    name = local.config_volume
  }
  volume {
    name = local.data_volume
  }
  container_definitions = jsonencode([
    merge(local.write_config, { logConfiguration = local.log.service }),
    merge(local.hardening, local.read_config, {
      name         = "relay-service"
      image        = local.image
      essential    = true
      portMappings = [{ containerPort = 8080, protocol = "tcp" }]
      environment = [
        { name = "RELAY_DB_HOST", value = aws_db_instance.relay.address },
        { name = "RELAY_DB_USER", value = "relay_service" },
        { name = "RELAY_DB_PATH", value = local.db_path },
        { name = "RELAY_DIRECTORY_FILE", value = "/run/relay/directory.json" },
        { name = "RELAY_LINK_BASE", value = var.link_base },
      ]
      logConfiguration = local.log.service
    }),
  ])
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
  volume {
    name = local.config_volume
  }
  volume {
    name = local.data_volume
  }
  container_definitions = jsonencode([
    merge(local.write_config, { logConfiguration = local.log.worker }),
    merge(local.hardening, local.read_config, {
      name      = "relay-worker"
      image     = local.image
      essential = true
      # Each loop also runs the escalation pass (ADR-017), which needs the projects and the link base.
      entryPoint = ["python", "-m", "relay.worker", "--db", local.db_path,
      "--directory", "/run/relay/directory.json", "--link-base", var.link_base]
      environment = [
        { name = "RELAY_DB_HOST", value = aws_db_instance.relay.address },
        { name = "RELAY_DB_USER", value = "relay_worker" },
        { name = "RELAY_TRIAGE_MODEL", value = var.triage_model_arn },
      ]
      logConfiguration = local.log.worker
    }),
  ])
}

# Schema migrations run once per deployment, as relay_migrator, before the service and the
# worker are updated (infra/runbooks/deploy.md). Neither application role can change the schema.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.migrate_task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  volume {
    name = local.data_volume
  }
  container_definitions = jsonencode([merge(local.hardening, {
    name        = "relay-migrate"
    image       = local.image
    essential   = true
    entryPoint  = ["python", "-m", "relay.service.migrate", "--db", local.db_path]
    mountPoints = [{ sourceVolume = "relay-data", containerPath = "/var/lib/relay", readOnly = false }]
    environment = [
      { name = "RELAY_DB_HOST", value = aws_db_instance.relay.address },
      { name = "RELAY_DB_USER", value = "relay_migrator" },
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
      # pip's defaults in an agent session (ADR-028): the mirror only, wheels only, hashes required.
      # github.com stays reachable for git, so a git+https requirement would fetch source; these refuse it.
      { name = "PIP_INDEX_URL", value = "https://pypi-mirror.relay.example/simple/" },
      { name = "PIP_ONLY_BINARY", value = ":all:" },
      { name = "PIP_REQUIRE_HASHES", value = "1" },
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

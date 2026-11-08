# Identity (ADR-012, ADR-014). Every principal here is a role with short-lived
# credentials: ECS tasks get theirs from the task role, CI gets theirs through
# OpenID Connect federation. This configuration creates no IAM users and no keys.

locals {
  ecs_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
    }]
  })
  oidc_provider_arn = "arn:aws:iam::${var.account_id}:oidc-provider/token.actions.githubusercontent.com"
  db_user_arn       = "arn:aws:rds-db:${var.region}:${var.account_id}:dbuser:*"
}

# --- ECS: pull images, write logs, inject the one secret ---------------------------

resource "aws_iam_role" "execution" {
  name                 = "${local.name}-execution"
  assume_role_policy   = local.ecs_trust
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "execution" {
  name = "pull-log-secret"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # GetAuthorizationToken does not support resource-level permissions; "*" is
      # the only valid resource. The policy checks allow it by name, and only it.
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      {
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = [
          "arn:aws:ecr:${var.region}:${var.account_id}:repository/relay",
          "arn:aws:ecr:${var.region}:${var.account_id}:repository/relay-egress-proxy",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:${var.account_id}:log-group:/relay/${var.env}/*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:relay/${var.env}/directory-??????"
      },
      {
        Effect    = "Allow"
        Action    = ["kms:Decrypt"]
        Resource  = "arn:aws:kms:${var.region}:${var.account_id}:key/*"
        Condition = { "ForAnyValue:StringEquals" = { "kms:ResourceAliases" = "alias/${local.name}" } }
      },
    ]
  })
}

# --- Task roles: one per process type, each with only what that process does -------

resource "aws_iam_role" "service_task" {
  name                 = "${local.name}-service"
  assume_role_policy   = local.ecs_trust
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "service_task" {
  name = "db-connect"
  role = aws_iam_role.service_task.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["rds-db:connect"], Resource = "${local.db_user_arn}/relay_service" }]
  })
}

resource "aws_iam_role" "worker_task" {
  name                 = "${local.name}-worker"
  assume_role_policy   = local.ecs_trust
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "worker_task" {
  name = "db-connect-and-model"
  role = aws_iam_role.worker_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["rds-db:connect"], Resource = "${local.db_user_arn}/relay_worker" },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = var.triage_model_arn },
    ]
  })
}

resource "aws_iam_role" "sandbox_task" {
  name                 = "${local.name}-sandbox"
  assume_role_policy   = local.ecs_trust
  max_session_duration = 3600
}

# Agent sessions may call the approved model and nothing else in AWS: no database,
# no secrets, no infrastructure (Chapter 3: no credentials worth stealing in a sandbox).
resource "aws_iam_role_policy" "sandbox_task" {
  name = "model-only"
  role = aws_iam_role.sandbox_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = var.triage_model_arn
    }]
  })
}

# --- CI: OpenID Connect federation, no stored keys -----------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Plan on pull requests: read-only, plus the state bucket.
resource "aws_iam_role" "ci_plan" {
  name                 = "${local.name}-ci-plan"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:pull_request"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ci_plan_readonly" {
  role       = aws_iam_role.ci_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "ci_plan_state" {
  name = "state-read-and-lock"
  role = aws_iam_role.ci_plan.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = "arn:aws:s3:::relay-tofu-state-${var.account_id}" },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::relay-tofu-state-${var.account_id}/${var.env}/*"
      },
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"],
        Resource = "arn:aws:kms:${var.region}:${var.account_id}:key/*",
      Condition = { "ForAnyValue:StringEquals" = { "kms:ResourceAliases" = "alias/relay-tofu-state" } } },
    ]
  })
}

# Apply and destroy: only from the protected "nonprod" GitHub environment, which
# requires a reviewer's approval of the run. The policy is broad by necessity and
# carries a waiver (Lab 11.1, data/policy.json, W-001) until it is narrowed from
# the actions CloudTrail records in its first month.
resource "aws_iam_role" "ci_apply" {
  name                 = "${local.name}-ci-apply"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:environment:nonprod"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "ci_apply" {
  name = "apply-relay-nonprod"
  role = aws_iam_role.ci_apply.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ec2:*", "ecs:*", "elasticloadbalancing:*", "rds:*", "secretsmanager:*", "kms:*", "logs:*",
          "ecr:*", "budgets:*", "s3:*", "servicediscovery:*", "route53:*"]
        Resource = "*"
      },
      {
        # IAM only on this environment's own roles and the OIDC provider, so the apply
        # role cannot create an administrator elsewhere in the account.
        Effect = "Allow"
        Action = ["iam:*"]
        Resource = [
          "arn:aws:iam::${var.account_id}:role/${local.name}-*",
          local.oidc_provider_arn,
        ]
      },
    ]
  })
}

# Agent identities, the kill switch and the audit trail's log groups (ADR-020 to ADR-022, 4.23.0).
#
# No agent holds a stored key. CI agents assume a role through GitHub's OIDC tokens, pinned to one
# repository and one protected environment; ECS agents get their task role's credentials. Each agent
# has its own role, so an alert, a CloudTrail record or a kill switch names exactly one agent.
# Relay's own tokens for agents are issued by Relay (src/relay/audit/identity.py), not here.
#
# Bootstrap set (infra/runbooks/bootstrap.md): aws_iam_policy.agent_quarantine, aws_iam_role.ci_killswitch
# and aws_iam_role_policy.ci_killswitch are created by the platform team. The apply role may not change
# them: the kill switch must not be something a pull request can weaken.

locals {
  agent_role_prefix = "arn:aws:iam::${var.account_id}:role/${local.name}"
  # Every role the kill switch may quarantine: the agent roles here, plus the sandbox and worker roles
  # from iam.tf, which agents also run as.
  quarantinable_roles = [
    "${local.agent_role_prefix}-agent-*",
    "${local.agent_role_prefix}-sandbox",
    "${local.agent_role_prefix}-worker",
  ]
  quarantine_policy_arn = "arn:aws:iam::${var.account_id}:policy/${local.name}-agent-quarantine"
}

# --- CI agent: explains failed runs; may call the approved model and nothing else -------------------

resource "aws_iam_role" "agent_ci_triage" {
  name                 = "${local.name}-agent-ci-triage"
  max_session_duration = 3600 # the minimum a role allows; the workflow requests 900 seconds
  permissions_boundary = aws_iam_policy.boundary.arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:environment:agent-ci-triage"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "agent_ci_triage" {
  name = "model-only"
  role = aws_iam_role.agent_ci_triage.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = var.triage_model_arn }]
  })
}

# --- Scheduled automation: an identity with no AWS permissions ---------------------------------------
# analytics-sync calls only Relay. Its role exists so that it can prove which workload it is (a signed
# sts:GetCallerIdentity request, which needs no permission) and exchange that proof for a Relay token.

resource "aws_iam_role" "agent_analytics_sync" {
  name                 = "${local.name}-agent-analytics-sync"
  assume_role_policy   = local.ecs_trust
  permissions_boundary = aws_iam_policy.boundary.arn
  max_session_duration = 3600
}

# --- The kill switch ---------------------------------------------------------------------------------

# Deny everything. Attached to an agent's role, it applies to sessions already issued for that role
# once the change propagates, so no credential the agent (or anyone who copied it) holds keeps working.
resource "aws_iam_policy" "agent_quarantine" {
  name        = "${local.name}-agent-quarantine"
  description = "Kill switch: attached to an agent role, denies every action"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Sid = "AgentQuarantined", Effect = "Deny", Action = "*", Resource = "*" }]
  })
}

# Assumable only from the protected "kill-switch" environment, which allows only the main branch. It can
# attach the quarantine policy, scale the agent's services to zero (so ECS does not replace stopped tasks)
# and stop tasks. It cannot detach anything, so restoring an agent is a person's change, reviewed by a
# second person (infra/runbooks/kill-switch.md).
resource "aws_iam_role" "ci_killswitch" {
  name                 = "${local.name}-ci-killswitch"
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
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:environment:kill-switch"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "ci_killswitch" {
  name = "quarantine-only"
  role = aws_iam_role.ci_killswitch.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AttachTheQuarantinePolicyOnly"
        Effect    = "Allow"
        Action    = ["iam:AttachRolePolicy"]
        Resource  = local.quarantinable_roles
        Condition = { ArnEquals = { "iam:PolicyARN" = local.quarantine_policy_arn } }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:ListAttachedRolePolicies", "iam:GetRole"]
        Resource = local.quarantinable_roles
      },
      {
        Effect    = "Allow"
        Action    = ["ecs:ListTasks", "ecs:StopTask", "ecs:UpdateService"]
        Resource  = "*"
        Condition = { ArnEquals = { "ecs:cluster" = "arn:aws:ecs:${var.region}:${var.account_id}:cluster/${local.name}" } }
      },
      {
        Sid      = "NeverUndo"
        Effect   = "Deny"
        Action   = ["iam:DetachRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:UpdateAssumeRolePolicy"]
        Resource = "*"
      },
    ]
  })
}

# --- The audit trail of agent actions (ADR-021) ------------------------------------------------------
# Records are shipped here from Relay's trail; anchors (the chain's head hash, hourly) go to a second
# group. Relay's workload roles may only create streams and put events (the boundary); none can delete.

resource "aws_cloudwatch_log_group" "agent_audit" {
  name              = "/relay/${var.env}/agent-audit"
  retention_in_days = 400
  kms_key_id        = aws_kms_key.relay.arn
}

resource "aws_cloudwatch_log_group" "agent_audit_anchors" {
  name              = "/relay/${var.env}/agent-audit-anchors"
  retention_in_days = 400
  kms_key_id        = aws_kms_key.relay.arn
}

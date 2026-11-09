"""Agent identity fitness checks on infra/agents.tf and the detection rules (4.23.0, ADR-020 and ADR-022).

Like the other infra tests, these read the configuration as text; they do not run OpenTofu.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_TF = (ROOT / "infra" / "agents.tf").read_text(encoding="utf-8")
IAM_TF = (ROOT / "infra" / "iam.tf").read_text(encoding="utf-8")


def block(text, kind, name):
    start = text.index(f'resource "{kind}" "{name}"')
    depth, i = 0, text.index("{", start)
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[start:j + 1]
    raise AssertionError(name)


def test_agent_roles_carry_the_boundary_and_one_hour_sessions():
    for name in ("agent_ci_triage", "agent_analytics_sync"):
        b = block(AGENTS_TF, "aws_iam_role", name)
        assert "permissions_boundary = aws_iam_policy.boundary.arn" in b
        assert "max_session_duration = 3600" in b


def test_every_oidc_subject_is_one_exact_environment():
    subjects = re.findall(r'"token\.actions\.githubusercontent\.com:sub" = "([^"]+)"', AGENTS_TF)
    assert subjects == ["repo:${var.github_repository}:environment:agent-ci-triage",
                        "repo:${var.github_repository}:environment:kill-switch"]
    assert "*" not in "".join(subjects)


def test_no_stored_keys_anywhere_in_infra():
    text = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "infra").rglob("*.tf"))
    assert "aws_iam_access_key" not in text and "aws_iam_user" not in text


def test_the_quarantine_policy_denies_everything():
    b = block(AGENTS_TF, "aws_iam_policy", "agent_quarantine")
    assert 'Effect = "Deny", Action = "*", Resource = "*"' in b


def test_the_kill_switch_can_attach_only_the_quarantine_policy_and_can_never_undo():
    b = block(AGENTS_TF, "aws_iam_role_policy", "ci_killswitch")
    assert 'ArnEquals = { "iam:PolicyARN" = local.quarantine_policy_arn }' in b
    allows = re.findall(r'Effect\s*=\s*"Allow"\s*Action\s*=\s*\[([^\]]*)\]', b)
    actions = {a.strip().strip('"') for group in allows for a in group.split(",")}
    assert actions == {"iam:AttachRolePolicy", "iam:ListAttachedRolePolicies", "iam:GetRole", "ecs:ListTasks",
                       "ecs:StopTask", "ecs:UpdateService"}
    assert '"iam:DetachRolePolicy"' in b.split('Sid      = "NeverUndo"')[1]


def test_the_apply_role_cannot_change_the_kill_switch():
    # The kill-switch role's name starts with the CI prefix that ci_apply is denied, and the quarantine
    # policy is a managed policy the apply role has no permission to create or change.
    assert 'name                 = "${local.name}-ci-killswitch"' in AGENTS_TF
    assert '"arn:aws:iam::${var.account_id}:role/${local.name}-ci-*"' in IAM_TF
    assert "iam:CreatePolicy" not in IAM_TF and "iam:CreatePolicyVersion" not in IAM_TF
    lift = block(IAM_TF, "aws_iam_role_policy", "ci_apply").split('Sid       = "NeverLiftTheQuarantine"')[1]
    assert 'Effect    = "Deny"' in lift and '"iam:DetachRolePolicy"' in lift and "agent-quarantine" in lift


def test_audit_log_groups_keep_400_days_and_are_encrypted():
    for name in ("agent_audit", "agent_audit_anchors"):
        b = block(AGENTS_TF, "aws_cloudwatch_log_group", name)
        assert "retention_in_days = 400" in b and "kms_key_id        = aws_kms_key.relay.arn" in b


def test_detection_rules_cover_exports_new_networks_read_volume_and_break_glass():
    rules = json.loads((ROOT / "infra" / "detection" / "rules.json").read_text(encoding="utf-8"))
    assert {r["id"]: r["kind"] for r in rules["rules"]} == {
        "DR-001": "count", "DR-002": "new_source", "DR-003": "sum_rows", "DR-004": "any"}
    assert rules["baseline_days"] == 28 and rules["evaluation_interval_seconds"] == 300

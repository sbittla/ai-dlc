"""The policy checks on small plans you can check by hand. Each test is one rule's behaviour."""

import json
from datetime import date

from conftest import POLICY, mkplan, rc, ref

from cloudcheck.policy import (Finding, apply_waivers, check_encryption, check_exposure, check_guardrails,
                               check_identity, check_network, check_tags, gate_status)

TAGS = {"app": "relay", "env": "nonprod", "owner": "sam.o", "cost-center": "relay-eng", "data-class": "Internal"}


def rules(findings):
    return [(f.rule, f.address, f.status) for f in findings]


def doc(*statements):
    return json.dumps({"Version": "2012-10-17", "Statement": list(statements)})


# ---------------------------------------------------------------- POL001, POL010 (provided)

def test_ingress_from_anywhere_fails_and_from_the_vpn_passes():
    p = mkplan(rc("aws_vpc_security_group_ingress_rule", "open", {"cidr_ipv4": "0.0.0.0/0", "ip_protocol": "tcp",
                                                                   "from_port": 8080, "to_port": 8080}),
               rc("aws_vpc_security_group_ingress_rule", "vpn", {"cidr_ipv4": "10.255.0.0/16", "ip_protocol": "tcp",
                                                                  "from_port": 443, "to_port": 443}))
    found = check_network(p, POLICY)
    assert [(f.address, f.message) for f in found] == [
        ("aws_vpc_security_group_ingress_rule.open", "ingress from 0.0.0.0/0 on tcp 8080")]


def test_unknown_source_address_cannot_be_checked():
    p = mkplan(rc("aws_vpc_security_group_ingress_rule", "later", {"ip_protocol": "tcp", "from_port": 22,
                                                                    "to_port": 22}, unknown={"cidr_ipv4": True}))
    assert rules(check_network(p, POLICY)) == [("POL001", "aws_vpc_security_group_ingress_rule.later",
                                                "cannot check")]


def test_egress_to_anywhere_only_from_the_allowlisted_group_and_port():
    def egress(name, group, port):
        return rc("aws_vpc_security_group_egress_rule", name, {"cidr_ipv4": "0.0.0.0/0", "ip_protocol": "tcp",
                                                               "from_port": port, "to_port": port},
                  unknown={"security_group_id": True}, config={"security_group_id": ref(group)})
    p = mkplan(egress("proxy", "aws_security_group.egress_proxy", 443),
               egress("proxy_http", "aws_security_group.egress_proxy", 80),
               egress("worker", "aws_security_group.worker", 443))
    assert [f.address for f in check_network(p, POLICY)] == [
        "aws_vpc_security_group_egress_rule.proxy_http", "aws_vpc_security_group_egress_rule.worker"]


def test_inline_rules_unknown_because_not_configured_are_not_judged():
    group = rc("aws_security_group", "service", {"name": "s"}, unknown={"ingress": True, "egress": True})
    assert check_network(mkplan(group), POLICY) == []


def test_inline_rules_in_a_security_group_are_checked():
    block = {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}
    allout = {"from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]}
    p = mkplan(rc("aws_security_group", "lab", {"ingress": [block], "egress": [allout]},
                  config={"ingress": [{}], "egress": [{}]}))
    assert [(f.rule, f.message) for f in check_network(p, POLICY)] == [
        ("POL001", "inline ingress from 0.0.0.0/0 on tcp 22"), ("POL010", "inline egress to 0.0.0.0/0 on all traffic")]


def test_internet_routes_only_in_allowlisted_tables():
    route = [{"cidr_block": "0.0.0.0/0", "gateway_id": ""}]
    p = mkplan(rc("aws_route_table", "public", {"route": route}, config={"route": [{}]}),
               rc("aws_route_table", "private", {"route": route}, config={"route": [{}]}))
    assert [f.address for f in check_network(p, POLICY)] == ["aws_route_table.private"]


# ---------------------------------------------------------------- TODO 1: POL002-POL004

def test_public_database_and_bucket_without_a_public_access_block():
    p = mkplan(rc("aws_db_instance", "db", {"publicly_accessible": True}),
               rc("aws_s3_bucket", "logs", {"bucket": "b"}),
               rc("aws_s3_bucket", "safe", {"bucket": "c"}),
               rc("aws_s3_bucket_public_access_block", "safe", {
                   "block_public_acls": True, "block_public_policy": True, "ignore_public_acls": True,
                   "restrict_public_buckets": True}, unknown={"bucket": True},
                  config={"bucket": ref("aws_s3_bucket.safe")}))
    assert rules(check_exposure(p, POLICY)) == [("POL002", "aws_db_instance.db", "fail"),
                                                ("POL002", "aws_s3_bucket.logs", "fail")]


def test_a_public_access_block_with_one_flag_off_does_not_count():
    p = mkplan(rc("aws_s3_bucket", "b", {}),
               rc("aws_s3_bucket_public_access_block", "b", {
                   "block_public_acls": True, "block_public_policy": False, "ignore_public_acls": True,
                   "restrict_public_buckets": True}, config={"bucket": ref("aws_s3_bucket.b")}))
    assert [f.message for f in check_exposure(p, POLICY)] == [
        "bucket has no public access block with all four settings on"]


def test_bucket_policy_open_to_anyone():
    p = mkplan(rc("aws_s3_bucket_policy", "w", {"policy": doc({"Effect": "Allow", "Principal": "*",
                                                              "Action": "s3:GetObject", "Resource": "x"})}))
    assert [f.message for f in check_exposure(p, POLICY)] == ["bucket policy allows anyone"]


def test_public_compute():
    p = mkplan(rc("aws_instance", "i", {"associate_public_ip_address": True}),
               rc("aws_ecs_service", "s", {"network_configuration": [{"assign_public_ip": True}]}),
               rc("aws_lb", "web", {"internal": False}),
               rc("aws_lb", "inside", {"internal": True}))
    assert [f.address for f in check_exposure(p, POLICY)] == ["aws_instance.i", "aws_ecs_service.s", "aws_lb.web"]


def test_model_calls_need_a_private_endpoint():
    grant = rc("aws_iam_role_policy", "worker", {"policy": doc({"Effect": "Allow", "Action": ["bedrock:InvokeModel"],
                                                               "Resource": "arn:model"})})
    assert [(f.address, f.message) for f in check_exposure(mkplan(grant), POLICY)] == [
        ("(plan)", "model calls are allowed but there is no private model endpoint")]


def test_model_endpoint_with_the_default_policy_or_no_private_dns():
    grant = rc("aws_iam_role_policy", "worker", {"policy": doc({"Effect": "Allow", "Action": ["bedrock:InvokeModel"],
                                                               "Resource": "arn:model"})})
    ep = rc("aws_vpc_endpoint", "bedrock", {"service_name": "com.amazonaws.us-east-1.bedrock-runtime",
                                            "vpc_endpoint_type": "Interface", "private_dns_enabled": False},
            unknown={"policy": True})
    assert [f.message for f in check_exposure(mkplan(grant, ep), POLICY)] == [
        "private DNS is off, so clients resolve the public model endpoint",
        "endpoint uses the default full-access policy"]


def test_no_model_grant_means_no_endpoint_needed():
    assert check_exposure(mkplan(rc("aws_iam_role_policy", "r", {"policy": doc(
        {"Effect": "Allow", "Action": ["logs:PutLogEvents"], "Resource": "arn:log"})})), POLICY) == []


# ---------------------------------------------------------------- TODO 2: POL005

def test_encryption_rules():
    kms = {"sse_algorithm": "aws:kms"}
    p = mkplan(rc("aws_db_instance", "db", {"storage_encrypted": False}),
               rc("aws_instance", "i", {"root_block_device": [{"encrypted": False}]}),
               rc("aws_s3_bucket", "plain", {}),
               rc("aws_s3_bucket", "kms", {}),
               rc("aws_s3_bucket_server_side_encryption_configuration", "kms",
                  {"rule": [{"apply_server_side_encryption_by_default": [kms]}]},
                  unknown={"rule": [{"apply_server_side_encryption_by_default": [{"kms_master_key_id": True}]}]},
                  config={"bucket": ref("aws_s3_bucket.kms")}),
               rc("aws_secretsmanager_secret", "default_key", {"name": "x"}),
               rc("aws_secretsmanager_secret", "cmk", {"name": "y"}, unknown={"kms_key_id": True}),
               rc("aws_cloudwatch_log_group", "g", {"kms_key_id": "arn:key"}),
               rc("aws_ecr_repository", "r", {"encryption_configuration": [{"encryption_type": "AES256"}]}),
               rc("aws_kms_key", "k", {"enable_key_rotation": False}))
    assert [f.address for f in check_encryption(p, POLICY)] == [
        "aws_db_instance.db", "aws_instance.i", "aws_s3_bucket.plain", "aws_secretsmanager_secret.default_key",
        "aws_ecr_repository.r", "aws_kms_key.k"]


def test_sse_s3_is_not_a_customer_managed_key():
    p = mkplan(rc("aws_s3_bucket", "b", {}),
               rc("aws_s3_bucket_server_side_encryption_configuration", "b",
                  {"rule": [{"apply_server_side_encryption_by_default": [{"sse_algorithm": "AES256"}]}]},
                  config={"bucket": ref("aws_s3_bucket.b")}))
    assert [f.message for f in check_encryption(p, POLICY)] == ["bucket is not encrypted with a customer-managed key"]


# ---------------------------------------------------------------- TODO 3: POL006

def test_tags_read_tags_all_not_tags():
    p = mkplan(rc("aws_vpc", "main", {"tags": None, "tags_all": dict(TAGS)}))
    assert check_tags(p, POLICY, date(2026, 11, 30)) == []


def test_missing_and_invalid_tags_in_one_finding():
    bad = {"app": "relay", "env": "staging", "data-class": "Secret"}
    p = mkplan(rc("aws_vpc", "a", {"tags_all": bad}), rc("aws_iam_role_policy", "untaggable", {"policy": "{}"}))
    assert [f.message for f in check_tags(p, POLICY, date(2026, 11, 30))] == [
        "missing owner, cost-center; env 'staging' not allowed; data-class 'Secret' not allowed"]


def test_confidential_data_only_in_prod_and_labs_need_an_expiry():
    conf = dict(TAGS, **{"data-class": "Confidential"})
    lab = dict(TAGS, env="lab")
    old = dict(TAGS, env="lab", expires="2026-11-01")
    p = mkplan(rc("aws_db_instance", "a", {"tags_all": conf}), rc("aws_db_instance", "b", {"tags_all": lab}),
               rc("aws_db_instance", "c", {"tags_all": old}),
               rc("aws_db_instance", "d", {"tags_all": dict(conf, env="prod")}))
    assert [(f.address, f.message) for f in check_tags(p, POLICY, date(2026, 11, 30))] == [
        ("aws_db_instance.a", "data-class 'Confidential' not allowed in nonprod"),
        ("aws_db_instance.b", "no expires tag"), ("aws_db_instance.c", "expired on 2026-11-01")]


def test_unknown_tags_cannot_be_checked():
    p = mkplan(rc("aws_vpc", "a", {}, unknown={"tags_all": True}))
    assert rules(check_tags(p, POLICY, date(2026, 11, 30))) == [("POL006", "aws_vpc.a", "cannot check")]


# ---------------------------------------------------------------- TODO 4: POL007-POL008

def test_wildcards_in_identity_policies():
    p = mkplan(
        rc("aws_iam_role_policy", "star", {"policy": doc({"Effect": "Allow", "Action": "*", "Resource": "*"})}),
        rc("aws_iam_role_policy", "service_star", {"policy": doc(
            {"Effect": "Allow", "Action": ["bedrock:*"], "Resource": "arn:model"})}),
        rc("aws_iam_role_policy", "not_action", {"policy": doc(
            {"Effect": "Allow", "NotAction": ["iam:*"], "Resource": "*"})}),
        rc("aws_iam_role_policy", "any_resource", {"policy": doc(
            {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "*"})}),
        rc("aws_iam_role_policy", "allowed", {"policy": doc(
            {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
            {"Effect": "Deny", "Action": "*", "Resource": "*"})}),
        rc("aws_iam_role_policy_attachment", "admin", {"policy_arn": "arn:aws:iam::aws:policy/AdministratorAccess"}))
    assert [(f.address, f.message) for f in check_identity(p, POLICY)] == [
        ("aws_iam_role_policy.star", "allows *"), ("aws_iam_role_policy.service_star", "allows bedrock:*"),
        ("aws_iam_role_policy.not_action", "allows everything except iam:*"),
        ("aws_iam_role_policy.any_resource", "allows s3:GetObject on any resource"),
        ("aws_iam_role_policy_attachment.admin", "attaches AdministratorAccess")]


def test_long_lived_credentials_and_oidc_trust():
    host = "token.actions.githubusercontent.com"

    def trust(conditions):
        return {"assume_role_policy": doc({"Effect": "Allow", "Principal": {"Federated": f"arn:oidc/{host}"},
                                           "Action": "sts:AssumeRoleWithWebIdentity", "Condition": conditions})}
    pinned = {"StringEquals": {f"{host}:aud": "sts.amazonaws.com", f"{host}:sub": "repo:o/r:pull_request"}}
    wide = {"StringEquals": {f"{host}:aud": "sts.amazonaws.com"}, "StringLike": {f"{host}:sub": "repo:o/*"}}
    p = mkplan(rc("aws_iam_user", "u", {"name": "x"}), rc("aws_iam_access_key", "k", {}),
               rc("aws_iam_role", "good", trust(pinned)), rc("aws_iam_role", "wide", trust(wide)),
               rc("aws_iam_role", "no_aud", trust({"StringEquals": {f"{host}:sub": "repo:o/r:ref:main"}})))
    assert [(f.address, f.message) for f in check_identity(p, POLICY)] == [
        ("aws_iam_user.u", "long-lived credentials: an IAM user"),
        ("aws_iam_access_key.k", "long-lived credentials: an access key"),
        ("aws_iam_role.wide", "OIDC subject not pinned to one repository and context"),
        ("aws_iam_role.no_aud", "OIDC audience not pinned")]


def test_unknown_policy_document_cannot_be_checked():
    p = mkplan(rc("aws_iam_role_policy", "later", {}, unknown={"policy": True}))
    assert rules(check_identity(p, POLICY)) == [("POL007", "aws_iam_role_policy.later", "cannot check")]


# ---------------------------------------------------------------- TODO 5: POL009, POL011, POL012

def budget(name, limit, kinds):
    notes = [{"notification_type": k, "subscriber_email_addresses": ["a@example.com"]} for k in kinds]
    return rc("aws_budgets_budget", name, {"budget_type": "COST", "time_unit": "MONTHLY", "limit_amount": limit,
                                           "notification": notes})


def test_no_budget_and_a_budget_without_a_forecast_alert():
    assert [(f.address, f.message) for f in check_guardrails(mkplan(), POLICY)] == [
        ("(plan)", "no monthly cost budget")]
    p = mkplan(budget("b", "300", ["ACTUAL"]), variables={"env": "nonprod"})
    assert [f.message for f in check_guardrails(p, POLICY)] == ["budget lacks an actual or a forecast alert"]


def test_budget_over_the_environment_ceiling():
    p = mkplan(budget("b", "900", ["ACTUAL", "FORECASTED"]), variables={"env": "nonprod"})
    assert [f.message for f in check_guardrails(p, POLICY)] == ["no budget at or under the nonprod ceiling of $500"]


def test_database_protection_in_order():
    db = rc("aws_db_instance", "db", {"deletion_protection": False, "backup_retention_period": 1,
                                      "skip_final_snapshot": True, "multi_az": False, "instance_class": "db.t4g.small"})
    p = mkplan(db, budget("b", "300", ["ACTUAL", "FORECASTED"]), variables={"env": "nonprod"})
    assert [f.message for f in check_guardrails(p, POLICY)] == [
        "deletion protection is off", "backups kept 1 days, fewer than 7", "no final snapshot on delete",
        "no standby in a second zone"]


def test_regions_and_sizes():
    p = mkplan(rc("aws_instance", "gpu", {"instance_type": "g5.12xlarge"}),
               rc("aws_instance", "small", {"instance_type": "t4g.small"}),
               budget("b", "100", ["ACTUAL", "FORECASTED"]), region="eu-central-1")
    assert [(f.address, f.message) for f in check_guardrails(p, POLICY)] == [
        ("(plan)", "region eu-central-1 not allowed"), ("aws_instance.gpu", "instance type g5.12xlarge not allowed")]


# ---------------------------------------------------------------- provided: waivers and the gate

def test_waiver_applies_until_it_expires():
    f = [Finding("POL007", "aws_iam_role_policy.ci_apply", "allows ec2:*")]
    assert apply_waivers(f, POLICY, date(2027, 2, 26))[0].status == "waived"
    late = apply_waivers(f, POLICY, date(2027, 2, 27))[0]
    assert late.status == "fail" and late.message.endswith("(waiver W-001 expired 2027-02-26)")


def test_gate_exit_codes():
    assert gate_status([]) == 0
    assert gate_status([Finding("POL001", "a", "m", "waived")]) == 0
    assert gate_status([Finding("POL001", "a", "m", "cannot check")]) == 2
    assert gate_status([Finding("POL001", "a", "m", "cannot check"), Finding("POL002", "b", "m")]) == 1

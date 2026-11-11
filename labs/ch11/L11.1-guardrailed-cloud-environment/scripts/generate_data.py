"""Write Lab 11.1's data/ folder. Deterministic: byte-identical on every platform.

    python scripts/generate_data.py

WHAT THIS GENERATES, AND WHAT IT IS NOT
The plan files are in the JSON format that `tofu show -json <planfile>` prints
(the format OpenTofu shares with Terraform, `format_version` 1.2). They were
NOT produced by `tofu plan`. This script builds them from a small model of each
resource, written to match `relay-repo/infra/*.tf`, so the lab runs with no
cloud account and no OpenTofu install. They are a faithful subset:

  kept      format_version, terraform_version, variables, planned_values,
            resource_changes (actions, before, after, after_unknown,
            before_sensitive, after_sensitive), configuration (provider
            config and each resource's top-level expressions: constant_value
            or references), timestamp, applyable, complete, errored
  omitted   prior_state, data sources, output_changes, relevant_attributes,
            checks, and most provider-computed attributes. Values that a real
            plan only knows after apply (ids, ARNs, anything derived from
            them) are unknown here too, marked in after_unknown.
  marked    terraform_version is "0.0.0-lab11.1-generated", so no reader can
            mistake these files for real tool output.

A real plan of the same configuration would contain more attributes per
resource (every provider default) and the same structure. Run the optional
live mode (README) to compare the checks against a real one.

Prices in data/prices/ are the authors' reading of AWS list prices for
us-east-1, dated 2026-11-10. They are assumptions to verify, not quotes.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ACCOUNT = "111122223333"
REGION = "us-east-1"
AWS = "registry.opentofu.org/hashicorp/aws"
FORMAT = "1.2"
TOOL_VERSION = "0.0.0-lab11.1-generated"
STAMP = "2026-11-30T09:00:00Z"


class Ref:
    """A value that refers to another resource: unknown in the plan, a reference in the configuration."""

    def __init__(self, address: str, attr: str = "id", suffix: str = ""):
        self.address, self.attr, self.suffix = address, attr, suffix


class Computed:
    """A value the provider computes at apply time, not set in the configuration."""


class Derived(Computed):
    """A configured value that depends on unknown values (for example jsonencode() of an ARN)."""


class KnownRef(Ref):
    """A reference to an attribute the target sets in its configuration (a name): known in the plan."""

    def __init__(self, address: str, attr: str, value: str):
        super().__init__(address, attr)
        self.value = value


UNKNOWN = Computed()
DERIVED = Derived()

# Attributes every resource of these types has, known only after apply.
COMPUTED = {
    "*": ["id"],
    "arn": ["arn"],
}
HAS_ARN = {"aws_vpc", "aws_subnet", "aws_internet_gateway", "aws_eip", "aws_route_table",
           "aws_default_security_group", "aws_security_group", "aws_vpc_security_group_ingress_rule",
           "aws_vpc_security_group_egress_rule", "aws_flow_log", "aws_vpc_endpoint", "aws_kms_key",
           "aws_kms_alias", "aws_db_subnet_group", "aws_db_parameter_group", "aws_db_instance",
           "aws_secretsmanager_secret", "aws_s3_bucket", "aws_ecr_repository", "aws_cloudwatch_log_group",
           "aws_ecs_cluster", "aws_ecs_task_definition", "aws_lb", "aws_lb_target_group", "aws_lb_listener",
           "aws_iam_role", "aws_iam_openid_connect_provider", "aws_budgets_budget", "aws_instance",
           "aws_iam_user", "aws_iam_policy", "aws_service_discovery_private_dns_namespace", "aws_service_discovery_service"}
EXTRA_COMPUTED = {
    "aws_vpc_endpoint": ["dns_entry", "network_interface_ids", "prefix_list_id"],
    "aws_security_group": ["ingress", "egress"],
    "aws_default_security_group": ["ingress", "egress"],
    "aws_db_instance": ["address", "endpoint", "master_user_secret"],
    "aws_lb": ["dns_name", "zone_id"],
    "aws_ecr_repository": ["repository_url", "registry_id"],
    "aws_kms_key": ["key_id"],
    "aws_ecs_task_definition": ["revision", "arn_without_revision"],
    "aws_eip": ["public_ip", "allocation_id"],
    "aws_nat_gateway": ["public_ip", "network_interface_id"],
    "aws_instance": ["public_ip", "private_ip"],
    "aws_iam_access_key": ["secret", "ses_smtp_password_v4"],
    "aws_iam_role": ["unique_id"],
}
TAGGABLE = HAS_ARN - {"aws_kms_alias", "aws_budgets_budget"} | {"aws_nat_gateway", "aws_ecs_service"}


def res(type_: str, rname: str, /, index: int | None = None, **attrs) -> dict:
    return {"type": type_, "name": rname, "index": index, "attrs": attrs}


def address(r: dict) -> str:
    base = f"{r['type']}.{r['name']}"
    return base if r["index"] is None else f"{base}[{r['index']}]"


def pol(*statements) -> str:
    """jsonencode() of an IAM policy, as OpenTofu would render it: compact, keys in order given."""
    return json.dumps({"Version": "2012-10-17", "Statement": list(statements)}, separators=(",", ":"))


# ----------------------------------------------------------------- plan rendering

def split(value):
    """(known value for `after`, unknown marker for `after_unknown`, or None when fully known)."""
    if isinstance(value, KnownRef):
        return value.value, None
    if isinstance(value, (Ref, Computed)):
        return None, True
    if isinstance(value, dict):
        known, unknown = {}, {}
        for k, v in value.items():
            kv, uv = split(v)
            if uv is True:
                unknown[k] = True
            else:
                known[k] = kv
                if uv is not None:
                    unknown[k] = uv
        return known, (unknown or None)
    if isinstance(value, list):
        known, unknown, any_unknown = [], [], False
        for v in value:
            kv, uv = split(v)
            known.append(kv)
            unknown.append(uv if uv is not None else False)
            any_unknown = any_unknown or uv is not None
        return known, (unknown if any_unknown else None)
    return value, None


def expression(value):
    """The configuration's view of a value: a constant, references, or nested blocks."""
    if isinstance(value, Ref):
        return {"references": [f"{value.address}.{value.attr}", value.address]}
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        return [{k: expression(v) for k, v in block.items()} for block in value]
    if isinstance(value, list) and any(isinstance(v, Ref) for v in value):
        refs = []
        for v in value:
            if isinstance(v, Ref):
                refs += [f"{v.address}.{v.attr}", v.address]
        return {"references": refs}
    if isinstance(value, Derived):
        return {"references": ["(derived from other resources)"]}
    return {"constant_value": value}


def full_attrs(r: dict, default_tags: dict) -> dict:
    """The resource's attributes as the plan would carry them: configured, computed, and tags_all."""
    attrs = dict(r["attrs"])
    sensitive = attrs.pop("_sensitive", [])
    for name in COMPUTED["*"] + (COMPUTED["arn"] if r["type"] in HAS_ARN else []) + \
            EXTRA_COMPUTED.get(r["type"], []):
        attrs.setdefault(name, UNKNOWN)
    if r["type"] in TAGGABLE:
        tags = attrs.get("tags") or {}
        attrs.setdefault("tags", None)
        attrs["tags_all"] = {**default_tags, **tags}
    return attrs, sensitive


def configured(r: dict) -> dict:
    return {k: expression(v) for k, v in r["attrs"].items()
            if not k.startswith("_") and (not isinstance(v, Computed) or isinstance(v, Derived))}


def plan(resources: list[dict], variables: dict, default_tags: dict, region_ref: bool = True) -> dict:
    planned, changes, config = [], [], []
    for r in resources:
        attrs, sensitive = full_attrs(r, default_tags)
        after, after_unknown = split(attrs)
        common = {"address": address(r), "mode": "managed", "type": r["type"], "name": r["name"]}
        if r["index"] is not None:
            common["index"] = r["index"]
        common["provider_name"] = AWS
        planned.append({**common, "schema_version": 0, "values": after,
                        "sensitive_values": {k: True for k in sensitive}})
        changes.append({**common, "change": {
            "actions": ["create"], "before": None, "after": after, "after_unknown": after_unknown or {},
            "before_sensitive": False, "after_sensitive": {k: True for k in sensitive}}})
        if r["index"] is None or r["index"] == 0:
            entry = {"address": f"{r['type']}.{r['name']}", "mode": "managed", "type": r["type"],
                     "name": r["name"], "provider_config_key": "aws", "expressions": configured(r),
                     "schema_version": 0}
            if r["index"] is not None:
                entry["count_expression"] = {"constant_value": 2}
            config.append(entry)
    provider = {"name": "aws", "full_name": AWS, "expressions": {
        "region": {"references": ["var.region"]} if region_ref else {"constant_value": REGION}}}
    if default_tags:
        provider["expressions"]["default_tags"] = [{"tags": {"constant_value": default_tags}}]
    return {
        "format_version": FORMAT,
        "terraform_version": TOOL_VERSION,
        "variables": {k: {"value": v} for k, v in variables.items()},
        "planned_values": {"root_module": {"resources": planned}},
        "resource_changes": changes,
        "configuration": {"provider_config": {"aws": provider}, "root_module": {"resources": config}},
        "timestamp": STAMP,
        "applyable": True,
        "complete": True,
        "errored": False,
    }


def fake_id(r: dict) -> str:
    digest = hashlib.sha256(address(r).encode("utf-8")).hexdigest()
    prefix = {"aws_vpc": "vpc-", "aws_subnet": "subnet-", "aws_security_group": "sg-", "aws_instance": "i-",
              "aws_db_instance": "db-", "aws_eip": "eipalloc-", "aws_nat_gateway": "nat-"}.get(r["type"], "")
    return prefix + digest[:17]


def resolve(value, ids: dict):
    if isinstance(value, KnownRef):
        return value.value
    if isinstance(value, Ref):
        return ids.get(value.address, "unknown") + value.suffix
    if isinstance(value, Computed):
        return "computed"
    if isinstance(value, dict):
        return {k: resolve(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, ids) for v in value]
    return value


def destroy_plan(resources: list[dict], variables: dict, default_tags: dict) -> dict:
    """`tofu plan -destroy` as JSON: every resource deleted; `before` holds its state."""
    ids = {address(r): fake_id(r) for r in resources}
    changes = []
    for r in resources:
        attrs, _ = full_attrs(r, default_tags)
        before = resolve(attrs, ids)
        before["id"] = ids[address(r)]
        common = {"address": address(r), "mode": "managed", "type": r["type"], "name": r["name"]}
        if r["index"] is not None:
            common["index"] = r["index"]
        common["provider_name"] = AWS
        changes.append({**common, "change": {"actions": ["delete"], "before": before, "after": None,
                                             "after_unknown": {}, "before_sensitive": {},
                                             "after_sensitive": False}})
    return {"format_version": FORMAT, "terraform_version": TOOL_VERSION,
            "variables": {k: {"value": v} for k, v in variables.items()},
            "planned_values": {"root_module": {}}, "resource_changes": changes,
            "configuration": {"provider_config": {"aws": {"name": "aws", "full_name": AWS}},
                              "root_module": {}},
            "timestamp": STAMP, "applyable": True, "complete": True, "errored": False}


# ----------------------------------------------------------------- Relay non-production

NAME = "relay-nonprod"
MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/example.triage-model-v1:0"
VARIABLES = {
    "region": REGION, "account_id": ACCOUNT, "env": "nonprod", "owner": "sam.o", "cost_center": "relay-eng",
    "data_class": "Internal", "azs": ["us-east-1a", "us-east-1b"], "vpc_cidr": "10.40.0.0/16",
    "vpn_cidr": "10.255.0.0/16", "image_tag": "4.21.0", "service_desired_count": 2, "worker_desired_count": 1,
    "proxy_desired_count": 1, "db_instance_class": "db.t4g.small", "db_multi_az": True,
    "triage_model_arn": MODEL_ARN,
    "certificate_arn": f"arn:aws:acm:us-east-1:{ACCOUNT}:certificate/00000000-0000-0000-0000-000000000000",
    "github_repository": "relay-example/relay", "budget_limit_usd": 300, "account_budget_limit_usd": 400,
    "budget_emails": ["relay-platform-alerts@example.com"],
}
DEFAULT_TAGS = {"app": "relay", "env": "nonprod", "owner": "sam.o", "cost-center": "relay-eng",
                "data-class": "Internal"}


def ecs_trust():
    return pol({"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}}})


def oidc_trust(sub: str):
    return pol({"Effect": "Allow",
                "Principal": {"Federated": f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                                               "token.actions.githubusercontent.com:sub": sub}}})


def subnet(name, az, cidr):
    return res("aws_subnet", name, vpc_id=Ref("aws_vpc.main"), availability_zone=az, cidr_block=cidr,
               map_public_ip_on_launch=False, tags={"Name": f"{NAME}-{name.replace('_', '-')}"})


def sg(name, description):
    return res("aws_security_group", name, name=f"{NAME}-{name.replace('_', '-')}", description=description,
               vpc_id=Ref("aws_vpc.main"))


def rule(kind, name, group, port, peer=None, cidr=None, prefix=None, description=None):
    attrs = {"security_group_id": Ref(f"aws_security_group.{group}"), "ip_protocol": "tcp",
             "from_port": port, "to_port": port}
    if description:
        attrs["description"] = description
    if peer:
        attrs["referenced_security_group_id"] = Ref(f"aws_security_group.{peer}")
    if cidr:
        attrs["cidr_ipv4"] = cidr
    if prefix:
        attrs["prefix_list_id"] = Ref(prefix, "prefix_list_id")
    return res(f"aws_vpc_security_group_{kind}_rule", name, **attrs)


def own_account(resources_too: bool) -> str:
    cond = {"aws:PrincipalAccount": ACCOUNT}
    if resources_too:
        cond["aws:ResourceAccount"] = ACCOUNT
    return pol({"Sid": "ThisAccountOnly" if resources_too else "ThisAccountsPrincipalsOnly", "Effect": "Allow",
                "Principal": "*", "Action": "*", "Resource": "*", "Condition": {"StringEquals": cond}})


S3_LAYERS = pol({"Sid": "EcrImageLayersOnly", "Effect": "Allow", "Principal": "*", "Action": ["s3:GetObject"],
                 "Resource": [f"arn:aws:s3:::prod-{REGION}-starport-layer-bucket/*"]})


def endpoint(name, service, policy=None):
    attrs = {"vpc_id": Ref("aws_vpc.main"), "service_name": f"com.amazonaws.{REGION}.{service}",
             "vpc_endpoint_type": "Interface", "private_dns_enabled": True,
             "subnet_ids": [Ref("aws_subnet.app_a"), Ref("aws_subnet.app_b")],
             "security_group_ids": [Ref("aws_security_group.endpoints")]}
    attrs["policy"] = policy if policy else UNKNOWN  # unset: AWS applies its default full-access policy
    return res("aws_vpc_endpoint", name, **attrs)


def task_def(name, cpu, memory, task_role=True):
    attrs = {"family": f"{NAME}-{name.replace('_', '-')}", "requires_compatibilities": ["FARGATE"],
             "network_mode": "awsvpc", "cpu": cpu, "memory": memory,
             "execution_role_arn": Ref("aws_iam_role.execution", "arn"),
             "runtime_platform": [{"cpu_architecture": "ARM64", "operating_system_family": "LINUX"}],
             "container_definitions": DERIVED}
    if task_role:
        attrs["task_role_arn"] = Ref(f"aws_iam_role.{name}_task", "arn")
    return res("aws_ecs_task_definition", name, **attrs)


def service(name, count_var, subnets, groups, lb=False, registry=False):
    attrs = {"name": f"{NAME}-{name.replace('_', '-')}", "cluster": Ref("aws_ecs_cluster.relay"),
             "task_definition": Ref(f"aws_ecs_task_definition.{name}", "arn"),
             "desired_count": VARIABLES[count_var], "launch_type": "FARGATE", "enable_execute_command": False,
             "propagate_tags": "SERVICE",
             "network_configuration": [{"subnets": [Ref(f"aws_subnet.{s}") for s in subnets],
                                        "security_groups": [Ref(f"aws_security_group.{g}") for g in groups],
                                        "assign_public_ip": False}]}
    if lb:
        attrs["load_balancer"] = [{"target_group_arn": Ref("aws_lb_target_group.service", "arn"),
                                   "container_name": "relay-service", "container_port": 8080}]
    if registry:
        attrs["service_registries"] = [{"registry_arn": Ref("aws_service_discovery_service.egress_proxy", "arn")}]
    return res("aws_ecs_service", name, **attrs)


def role(name, trust):
    return res("aws_iam_role", name, name=f"{NAME}-{name.replace('_task', '').replace('_', '-')}",
               assume_role_policy=trust, permissions_boundary=Ref("aws_iam_policy.boundary", "arn"),
               max_session_duration=3600)


BOUNDARY_ARN = f"arn:aws:iam::{ACCOUNT}:policy/{NAME}-boundary"
OIDC_ARN = f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"


def boundary():
    return res("aws_iam_policy", "boundary", name=f"{NAME}-boundary",
               description="Maximum permissions of any Relay nonprod workload role", policy=pol(
                   {"Effect": "Allow", "Action": ["rds-db:connect"],
                    "Resource": f"arn:aws:rds-db:{REGION}:{ACCOUNT}:dbuser:*/relay_*"},
                   {"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                    "Resource": MODEL_ARN},
                   {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
                   {"Effect": "Allow",
                    "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"],
                    "Resource": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/relay*"},
                   {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                    "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/relay/nonprod/*:*"},
                   {"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"],
                    "Resource": f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:relay/nonprod/*"},
                   {"Effect": "Allow", "Action": ["kms:Decrypt"], "Resource": f"arn:aws:kms:{REGION}:{ACCOUNT}:key/*"}))


APPLY_STATEMENTS = (
    {"Effect": "Allow", "Action": ["ec2:*", "ecs:*", "elasticloadbalancing:*", "rds:*", "secretsmanager:*",
                                   "kms:*", "logs:*", "ecr:*", "budgets:*", "s3:*", "servicediscovery:*",
                                   "route53:*"], "Resource": "*"},
    {"Sid": "BoundedRolesOnly", "Effect": "Allow",
     "Action": ["iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:PutRolePermissionsBoundary"],
     "Resource": f"arn:aws:iam::{ACCOUNT}:role/{NAME}-*",
     "Condition": {"StringEquals": {"iam:PermissionsBoundary": BOUNDARY_ARN}}},
    {"Effect": "Allow",
     "Action": ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
                "iam:ListInstanceProfilesForRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateRole",
                "iam:UpdateAssumeRolePolicy", "iam:DeleteRolePolicy", "iam:DetachRolePolicy", "iam:DeleteRole"],
     "Resource": f"arn:aws:iam::{ACCOUNT}:role/{NAME}-*"},
    {"Effect": "Allow", "Action": ["iam:PassRole"], "Resource": f"arn:aws:iam::{ACCOUNT}:role/{NAME}-*",
     "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}},
    {"Effect": "Allow",
     "Action": ["iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions", "iam:GetOpenIDConnectProvider"],
     "Resource": [BOUNDARY_ARN, OIDC_ARN]},
    {"Effect": "Allow", "Action": ["iam:CreateServiceLinkedRole"],
     "Resource": f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/*",
     "Condition": {"StringEquals": {"iam:AWSServiceName": ["ecs.amazonaws.com", "elasticloadbalancing.amazonaws.com",
                                                           "rds.amazonaws.com"]}}},
    {"Sid": "NeverTheCiRolesOrTheBoundary", "Effect": "Deny", "NotAction": ["iam:Get*", "iam:List*"],
     "Resource": [f"arn:aws:iam::{ACCOUNT}:role/{NAME}-ci-*", BOUNDARY_ARN, OIDC_ARN]},
    {"Sid": "NeverAdministratorPolicies", "Effect": "Deny", "Action": ["iam:AttachRolePolicy"], "Resource": "*",
     "Condition": {"ArnLike": {"iam:PolicyARN": ["arn:aws:iam::aws:policy/AdministratorAccess",
                                                 "arn:aws:iam::aws:policy/PowerUserAccess",
                                                 "arn:aws:iam::aws:policy/IAMFullAccess"]}}},
    {"Effect": "Deny", "Action": ["iam:DeleteRolePermissionsBoundary"], "Resource": "*"},
)


def nonprod() -> list[dict]:
    rt = "aws_route_table_association"
    db_user = f"arn:aws:rds-db:{REGION}:{ACCOUNT}:dbuser:*"
    out = [
        res("aws_vpc", "main", cidr_block="10.40.0.0/16", enable_dns_support=True, enable_dns_hostnames=True,
            tags={"Name": NAME}),
        res("aws_default_security_group", "main", vpc_id=Ref("aws_vpc.main")),
        subnet("app_a", "us-east-1a", "10.40.1.0/24"), subnet("app_b", "us-east-1b", "10.40.2.0/24"),
        subnet("data_a", "us-east-1a", "10.40.11.0/24"), subnet("data_b", "us-east-1b", "10.40.12.0/24"),
        subnet("sandbox_a", "us-east-1a", "10.40.21.0/24"), subnet("egress_a", "us-east-1a", "10.40.31.0/24"),
        subnet("public_a", "us-east-1a", "10.40.41.0/28"),
        res("aws_internet_gateway", "main", vpc_id=Ref("aws_vpc.main")),
        res("aws_eip", "nat", domain="vpc"),
        res("aws_nat_gateway", "egress", allocation_id=Ref("aws_eip.nat"), subnet_id=Ref("aws_subnet.public_a"),
            connectivity_type="public"),
        res("aws_route_table", "private", vpc_id=Ref("aws_vpc.main"), route=UNKNOWN),
        res("aws_route_table", "sandbox", vpc_id=Ref("aws_vpc.main"), route=UNKNOWN),
        res("aws_route_table", "egress", vpc_id=Ref("aws_vpc.main"),
            route=[{"cidr_block": "0.0.0.0/0", "nat_gateway_id": Ref("aws_nat_gateway.egress"), "gateway_id": ""}]),
        res("aws_route_table", "public", vpc_id=Ref("aws_vpc.main"),
            route=[{"cidr_block": "0.0.0.0/0", "nat_gateway_id": "", "gateway_id": Ref("aws_internet_gateway.main")}]),
    ]
    for s, table in (("app_a", "private"), ("app_b", "private"), ("data_a", "private"), ("data_b", "private"),
                     ("sandbox_a", "sandbox"), ("egress_a", "egress"), ("public_a", "public")):
        out.append(res(rt, s, subnet_id=Ref(f"aws_subnet.{s}"), route_table_id=Ref(f"aws_route_table.{table}")))
    out.append(res("aws_flow_log", "main", vpc_id=Ref("aws_vpc.main"), traffic_type="ALL",
                   log_destination_type="s3", log_destination=Ref("aws_s3_bucket.flow_logs", "arn")))
    out += [
        endpoint("bedrock_runtime", "bedrock-runtime", pol({
            "Sid": "ApprovedModelOnly", "Effect": "Allow",
            "Principal": {"AWS": [f"arn:aws:iam::{ACCOUNT}:role/{NAME}-worker",
                                  f"arn:aws:iam::{ACCOUNT}:role/{NAME}-sandbox"]},
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": [MODEL_ARN]})),
        endpoint("secretsmanager", "secretsmanager", own_account(True)), endpoint("logs", "logs", own_account(True)),
        endpoint("ecr_api", "ecr.api", own_account(False)), endpoint("ecr_dkr", "ecr.dkr", own_account(False)),
        res("aws_vpc_endpoint", "s3", vpc_id=Ref("aws_vpc.main"), service_name=f"com.amazonaws.{REGION}.s3",
            vpc_endpoint_type="Gateway",
            route_table_ids=[Ref("aws_route_table.private"), Ref("aws_route_table.sandbox"),
                             Ref("aws_route_table.egress")], policy=S3_LAYERS),
    ]
    out += [sg("alb", "Internal load balancer"), sg("service", "Relay HTTP service tasks"),
            sg("worker", "Relay triage worker tasks"),
            sg("tasks", "Every ECS task: image pulls, logs and secrets through endpoints"),
            sg("endpoints", "Interface VPC endpoints"), sg("db", "PostgreSQL"),
            sg("sandbox", "Background agent sessions"),
            sg("egress_proxy", "Allowlisting HTTPS proxy for agent sandboxes")]
    out += [
        rule("ingress", "alb_https_vpn", "alb", 443, cidr="10.255.0.0/16", description="HTTPS from the company VPN only"),
        rule("egress", "alb_to_service", "alb", 8080, peer="service"),
        rule("ingress", "service_from_alb", "service", 8080, peer="alb"),
        rule("egress", "service_to_db", "service", 5432, peer="db"),
        rule("egress", "worker_to_db", "worker", 5432, peer="db"),
        rule("ingress", "db_from_service", "db", 5432, peer="service"),
        rule("ingress", "db_from_worker", "db", 5432, peer="worker"),
        rule("ingress", "endpoints_from_tasks", "endpoints", 443, peer="tasks"),
        rule("ingress", "endpoints_from_sandbox", "endpoints", 443, peer="sandbox"),
        rule("egress", "tasks_to_endpoints", "tasks", 443, peer="endpoints"),
        rule("egress", "tasks_to_s3", "tasks", 443, prefix="aws_vpc_endpoint.s3"),
        rule("egress", "sandbox_to_endpoints", "sandbox", 443, peer="endpoints"),
        rule("egress", "sandbox_to_s3", "sandbox", 443, prefix="aws_vpc_endpoint.s3"),
        rule("egress", "sandbox_to_proxy", "sandbox", 3128, peer="egress_proxy"),
        rule("ingress", "proxy_from_sandbox", "egress_proxy", 3128, peer="sandbox"),
        rule("egress", "proxy_https_internet", "egress_proxy", 443, cidr="0.0.0.0/0",
             description="Allowlisted exception: the proxy forwards to allowlisted domains only"),
    ]
    kms = Ref("aws_kms_key.relay", "arn")
    for repo, name in (("relay", "relay"), ("egress_proxy", "relay-egress-proxy")):
        out.append(res("aws_ecr_repository", repo, name=name, image_tag_mutability="IMMUTABLE", force_delete=False,
                       image_scanning_configuration=[{"scan_on_push": True}],
                       encryption_configuration=[{"encryption_type": "KMS", "kms_key": kms}]))
    for g in ("service", "worker", "egress_proxy", "sandbox"):
        out.append(res("aws_cloudwatch_log_group", g, name=f"/relay/nonprod/{g.replace('_', '-')}",
                       retention_in_days=30, kms_key_id=kms))
    out += [
        res("aws_ecs_cluster", "relay", name=NAME, setting=[{"name": "containerInsights", "value": "enabled"}]),
        task_def("service", "512", "1024"), task_def("worker", "256", "512"),
        task_def("egress_proxy", "256", "512", task_role=False), task_def("sandbox", "1024", "2048"),
        service("service", "service_desired_count", ["app_a", "app_b"], ["service", "tasks"], lb=True),
        service("worker", "worker_desired_count", ["app_a", "app_b"], ["worker", "tasks"]),
        service("egress_proxy", "proxy_desired_count", ["egress_a"], ["egress_proxy", "tasks"], registry=True),
        res("aws_service_discovery_private_dns_namespace", "internal", name=f"{NAME}.internal",
            vpc=Ref("aws_vpc.main")),
        res("aws_service_discovery_service", "egress_proxy", name="egress-proxy",
            dns_config=[{"namespace_id": Ref("aws_service_discovery_private_dns_namespace.internal"),
                         "dns_records": [{"type": "A", "ttl": 10}]}]),
        res("aws_lb", "internal", name=f"{NAME}-internal", internal=True, load_balancer_type="application",
            drop_invalid_header_fields=True, subnets=[Ref("aws_subnet.app_a"), Ref("aws_subnet.app_b")],
            security_groups=[Ref("aws_security_group.alb")]),
        res("aws_lb_target_group", "service", name=f"{NAME}-service", port=8080, protocol="HTTP", target_type="ip",
            vpc_id=Ref("aws_vpc.main"), health_check=[{"path": "/healthz", "matcher": "200"}]),
        res("aws_lb_listener", "https", load_balancer_arn=Ref("aws_lb.internal", "arn"), port=443, protocol="HTTPS",
            ssl_policy="ELBSecurityPolicy-TLS13-1-2-2021-06", certificate_arn=VARIABLES["certificate_arn"],
            default_action=[{"type": "forward", "target_group_arn": Ref("aws_lb_target_group.service", "arn")}]),
    ]
    out += [
        boundary(),
        role("execution", ecs_trust()),
        res("aws_iam_role_policy", "execution", name="pull-log-secret", role=Ref("aws_iam_role.execution"), policy=pol(
            {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
            {"Effect": "Allow",
             "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"],
             "Resource": [f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/relay",
                          f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/relay-egress-proxy"]},
            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
             "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/relay/nonprod/*:*"},
            {"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"],
             "Resource": f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:relay/nonprod/directory-??????"},
            {"Effect": "Allow", "Action": ["kms:Decrypt"], "Resource": f"arn:aws:kms:{REGION}:{ACCOUNT}:key/*",
             "Condition": {"ForAnyValue:StringEquals": {"kms:ResourceAliases": f"alias/{NAME}"}}})),
        role("service_task", ecs_trust()),
        res("aws_iam_role_policy", "service_task", name="db-connect", role=Ref("aws_iam_role.service_task"),
            policy=pol({"Effect": "Allow", "Action": ["rds-db:connect"], "Resource": f"{db_user}/relay_service"})),
        role("worker_task", ecs_trust()),
        res("aws_iam_role_policy", "worker_task", name="db-connect-and-model", role=Ref("aws_iam_role.worker_task"),
            policy=pol({"Effect": "Allow", "Action": ["rds-db:connect"], "Resource": f"{db_user}/relay_worker"},
                       {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": MODEL_ARN})),
        role("sandbox_task", ecs_trust()),
        res("aws_iam_role_policy", "sandbox_task", name="model-only", role=Ref("aws_iam_role.sandbox_task"),
            policy=pol({"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        "Resource": MODEL_ARN})),
        res("aws_iam_openid_connect_provider", "github", url="https://token.actions.githubusercontent.com",
            client_id_list=["sts.amazonaws.com"]),
        res("aws_iam_role", "ci_plan", name=f"{NAME}-ci-plan", max_session_duration=3600,
            assume_role_policy=oidc_trust("repo:relay-example/relay:pull_request")),
        res("aws_iam_role_policy_attachment", "ci_plan_readonly", role=KnownRef("aws_iam_role.ci_plan", "name",
                                                                                 f"{NAME}-ci-plan"),
            policy_arn="arn:aws:iam::aws:policy/ReadOnlyAccess"),
        res("aws_iam_role_policy", "ci_plan_state", name="state-read-and-lock", role=Ref("aws_iam_role.ci_plan"),
            policy=pol(
                {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::relay-tofu-state-{ACCOUNT}"},
                {"Effect": "Allow", "Action": ["s3:GetObject"],
                 "Resource": f"arn:aws:s3:::relay-tofu-state-{ACCOUNT}/nonprod/*"},
                {"Effect": "Allow", "Action": ["s3:PutObject", "s3:DeleteObject"],
                 "Resource": f"arn:aws:s3:::relay-tofu-state-{ACCOUNT}/nonprod/relay.tfstate.tflock"},
                {"Effect": "Allow", "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
                 "Resource": f"arn:aws:kms:{REGION}:{ACCOUNT}:key/*",
                 "Condition": {"ForAnyValue:StringEquals": {"kms:ResourceAliases": "alias/relay-tofu-state"}}},
                {"Effect": "Deny", "Action": ["s3:GetObject"],
                 "NotResource": [f"arn:aws:s3:::relay-tofu-state-{ACCOUNT}/nonprod/*"]},
                {"Effect": "Deny", "Action": ["secretsmanager:GetSecretValue"], "Resource": "*"})),
        res("aws_iam_role", "ci_apply", name=f"{NAME}-ci-apply", max_session_duration=3600,
            assume_role_policy=oidc_trust("repo:relay-example/relay:environment:nonprod")),
        res("aws_iam_role_policy", "ci_apply", name="apply-relay-nonprod", role=Ref("aws_iam_role.ci_apply"),
            policy=pol(*APPLY_STATEMENTS)),
    ]
    out += [
        res("aws_kms_key", "relay", description="Relay nonprod: database, secrets, logs, images",
            enable_key_rotation=True, deletion_window_in_days=30, policy=pol(
                {"Sid": "AccountAdministersTheKeyThroughIAM", "Effect": "Allow",
                 "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"}, "Action": "kms:*", "Resource": "*"},
                {"Sid": "CloudWatchLogs", "Effect": "Allow", "Principal": {"Service": f"logs.{REGION}.amazonaws.com"},
                 "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"],
                 "Resource": "*", "Condition": {"ArnLike": {
                     "kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/relay/nonprod/*"}}},
                {"Sid": "VpcFlowLogDelivery", "Effect": "Allow", "Principal": {"Service": "delivery.logs.amazonaws.com"},
                 "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"],
                 "Resource": "*", "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}}})),
        res("aws_kms_alias", "relay", name=f"alias/{NAME}", target_key_id=Ref("aws_kms_key.relay", "key_id")),
        res("aws_db_subnet_group", "relay", name=NAME, subnet_ids=[Ref("aws_subnet.data_a"), Ref("aws_subnet.data_b")]),
        res("aws_db_parameter_group", "relay", name=f"{NAME}-pg16", family="postgres16",
            parameter=[{"name": "rds.force_ssl", "value": "1"}, {"name": "log_connections", "value": "1"}]),
        res("aws_db_instance", "relay", identifier=NAME, engine="postgres", engine_version="16",
            instance_class="db.t4g.small", allocated_storage=20, max_allocated_storage=100, storage_type="gp3",
            storage_encrypted=True, kms_key_id=kms, db_name="relay", username="relay_admin",
            manage_master_user_password=True, master_user_secret_kms_key_id=kms,
            iam_database_authentication_enabled=True, multi_az=True, publicly_accessible=False,
            db_subnet_group_name=KnownRef("aws_db_subnet_group.relay", "name", NAME),
            parameter_group_name=KnownRef("aws_db_parameter_group.relay", "name", f"{NAME}-pg16"),
            vpc_security_group_ids=[Ref("aws_security_group.db")], port=5432, backup_retention_period=7,
            backup_window="03:00-04:00", copy_tags_to_snapshot=True, deletion_protection=True,
            skip_final_snapshot=False, final_snapshot_identifier=f"{NAME}-final", auto_minor_version_upgrade=True),
        res("aws_secretsmanager_secret", "directory", name="relay/nonprod/directory", kms_key_id=kms,
            recovery_window_in_days=7),
        res("aws_s3_bucket", "flow_logs", bucket=f"{NAME}-flow-logs-{ACCOUNT}", force_destroy=False),
        res("aws_s3_bucket_public_access_block", "flow_logs", bucket=Ref("aws_s3_bucket.flow_logs"),
            block_public_acls=True, block_public_policy=True, ignore_public_acls=True, restrict_public_buckets=True),
        res("aws_s3_bucket_server_side_encryption_configuration", "flow_logs", bucket=Ref("aws_s3_bucket.flow_logs"),
            rule=[{"apply_server_side_encryption_by_default": [{"sse_algorithm": "aws:kms", "kms_master_key_id": kms}],
                   "bucket_key_enabled": True}]),
        res("aws_s3_bucket_lifecycle_configuration", "flow_logs", bucket=Ref("aws_s3_bucket.flow_logs"),
            rule=[{"id": "expire-30-days", "status": "Enabled", "filter": [{}], "expiration": [{"days": 30}]}]),
    ]
    emails = VARIABLES["budget_emails"]

    def note(threshold, kind):
        return {"comparison_operator": "GREATER_THAN", "threshold": threshold, "threshold_type": "PERCENTAGE",
                "notification_type": kind, "subscriber_email_addresses": emails}
    out += [
        res("aws_budgets_budget", "nonprod", name=f"{NAME}-monthly", budget_type="COST", limit_amount="300",
            limit_unit="USD", time_unit="MONTHLY", cost_filter=[{"name": "TagKeyValue", "values": ["user:env$nonprod"]}],
            notification=[note(50, "ACTUAL"), note(80, "ACTUAL"), note(100, "FORECASTED")]),
        res("aws_budgets_budget", "account", name=f"{NAME}-account-monthly", budget_type="COST", limit_amount="400",
            limit_unit="USD", time_unit="MONTHLY", notification=[note(100, "ACTUAL"), note(100, "FORECASTED")]),
    ]
    return out


# ----------------------------------------------------------------- the incident's lab environment

def incident() -> list[dict]:
    """The weekend lab, reconstructed as code from the console's records after the incident (composite)."""
    admin = pol({"Effect": "Allow", "Action": "*", "Resource": "*"})
    out = [
        res("aws_security_group", "model_lab", name="model-lab", description="model lab",
            vpc_id="vpc-0default00000000",
            ingress=[{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"],
                      "ipv6_cidr_blocks": [], "security_groups": [], "self": False, "prefix_list_ids": [],
                      "description": ""},
                     {"from_port": 8000, "to_port": 8000, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"],
                      "ipv6_cidr_blocks": [], "security_groups": [], "self": False, "prefix_list_ids": [],
                      "description": "model API"}],
            egress=[{"from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"],
                     "ipv6_cidr_blocks": [], "security_groups": [], "self": False, "prefix_list_ids": [],
                     "description": ""}]),
    ]
    for i in (0, 1):
        out.append(res("aws_instance", "model", index=i, ami="ami-0example000000000", instance_type="g5.48xlarge",
                       associate_public_ip_address=True, key_name="lab-key", subnet_id="subnet-0default0000000a",
                       vpc_security_group_ids=[Ref("aws_security_group.model_lab")],
                       root_block_device=[{"volume_size": 1000, "volume_type": "gp3", "encrypted": False}]))
    out += [
        res("aws_db_instance", "lab", identifier="model-lab-db", engine="postgres", engine_version="16",
            instance_class="db.r6g.4xlarge", allocated_storage=500, storage_type="gp3", storage_encrypted=False,
            username="labadmin", password="lab-password-not-real", _sensitive=["password"],
            multi_az=False, publicly_accessible=True,
            vpc_security_group_ids=[Ref("aws_security_group.model_lab")], backup_retention_period=0,
            deletion_protection=False, skip_final_snapshot=True, iam_database_authentication_enabled=False),
        res("aws_s3_bucket", "weights", bucket="model-lab-weights-111122223333", force_destroy=True),
        res("aws_s3_bucket_policy", "weights", bucket=Ref("aws_s3_bucket.weights"),
            policy=pol({"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
                        "Resource": "arn:aws:s3:::model-lab-weights-111122223333/*"})),
        res("aws_iam_user", "lab", name="model-lab"),
        res("aws_iam_access_key", "lab", user=Ref("aws_iam_user.lab", "name")),
        res("aws_iam_user_policy", "lab", name="lab-admin", user=Ref("aws_iam_user.lab", "name"), policy=admin),
    ]
    return out


# ----------------------------------------------------------------- seeded variants

def find(resources, addr):
    for r in resources:
        if address(r) == addr:
            return r
    raise KeyError(addr)


def without(resources, *addrs):
    return [r for r in resources if address(r) not in addrs]


def drop_resource_tags(resources: list[dict]) -> None:
    for r in resources:
        r["attrs"].pop("tags", None)


def seeded() -> list[tuple[dict, list[dict], dict]]:
    """(manifest entry, resources, default tags) for each seeded case. One change each, to a fresh copy."""
    cases = []

    def case(id_, change, kind, expected, note, mutate, tags=DEFAULT_TAGS):
        rs = copy.deepcopy(nonprod())
        rs = mutate(rs) or rs
        cases.append(({"id": id_, "change": change, "kind": kind, "expected_rules": expected, "note": note},
                      rs, tags))

    def set_attr(addr, **kv):
        def m(rs):
            find(rs, addr)["attrs"].update(kv)
        return m

    case("S01", "The database is made publicly accessible", "violation", ["POL002"],
         "Private subnets alone do not stop this: a public flag on the instance is enough to ask for a public address.",
         set_attr("aws_db_instance.relay", publicly_accessible=True))
    case("S02", "The service accepts port 8080 from 0.0.0.0/0", "violation", ["POL001"],
         "A typical debugging shortcut.",
         lambda rs: rs.append(rule("ingress", "service_debug", "service", 8080, cidr="0.0.0.0/0")))
    case("S03", "The flow-log bucket's encryption configuration is removed", "violation", ["POL005"],
         "S3 still encrypts new objects with its own keys; the policy requires the customer-managed key.",
         lambda rs: without(rs, "aws_s3_bucket_server_side_encryption_configuration.flow_logs"))
    case("S04", "The cost-center tag is dropped from the provider's default tags", "violation", ["POL006"],
         "One line in providers.tf; every taggable resource loses the tag.", lambda rs: None,
         tags={k: v for k, v in DEFAULT_TAGS.items() if k != "cost-center"})
    case("S05", "The worker may call any Bedrock action on any resource", "violation", ["POL007"],
         "An agent's fix for an AccessDenied error.",
         set_attr("aws_iam_role_policy.worker_task", policy=pol(
             {"Effect": "Allow", "Action": ["rds-db:connect"],
              "Resource": f"arn:aws:rds-db:{REGION}:{ACCOUNT}:dbuser:*/relay_worker"},
             {"Effect": "Allow", "Action": ["bedrock:*"], "Resource": "*"})))
    case("S06", "Both budgets are removed", "violation", ["POL009"],
         "Spend would still be visible in Cost Explorer, to anyone who looked.",
         lambda rs: without(rs, "aws_budgets_budget.nonprod", "aws_budgets_budget.account"))
    case("S07", "The worker may send HTTPS to 0.0.0.0/0", "violation", ["POL010"],
         "The route table still has no way out, so this rule alone opens nothing today; it is still refused.",
         lambda rs: rs.append(rule("egress", "worker_https_anywhere", "worker", 443, cidr="0.0.0.0/0")))
    case("S08", "Deletion protection off and backups disabled", "violation", ["POL011"],
         "Two changes to one resource, the kind that makes a teardown quicker.",
         set_attr("aws_db_instance.relay", deletion_protection=False, backup_retention_period=0))
    case("S09", "The Bedrock endpoint is removed", "violation", ["POL004"],
         "With no internet route, model calls would fail rather than leak; the rule names the cause.",
         lambda rs: without(rs, "aws_vpc_endpoint.bedrock_runtime"))
    case("S10", "The service tasks get public IP addresses", "violation", ["POL003"],
         "A common fix for image pulls failing in a subnet with no route out.",
         lambda rs: find(rs, "aws_ecs_service.service")["attrs"]["network_configuration"][0].update(
             assign_public_ip=True))
    case("S11", "CI's apply role trusts every repository in the organization", "violation", ["POL008"],
         "A wildcard in the OIDC subject lets any repository's workflow assume the role.",
         set_attr("aws_iam_role.ci_apply", assume_role_policy=pol(
             {"Effect": "Allow",
              "Principal": {"Federated": f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"},
              "Action": "sts:AssumeRoleWithWebIdentity",
              "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                            "StringLike": {"token.actions.githubusercontent.com:sub": "repo:relay-example/*"}}})))
    case("S12", "A GPU instance is added for a model experiment", "violation", ["POL012"],
         "The organization's guardrail would also refuse it at apply time.",
         lambda rs: rs.append(res("aws_instance", "experiment", ami="ami-0example000000000",
                                  instance_type="g5.12xlarge", associate_public_ip_address=False,
                                  subnet_id=Ref("aws_subnet.app_a"),
                                  root_block_device=[{"volume_size": 200, "volume_type": "gp3", "encrypted": True}])))
    case("S13", "SSH to the service from a new Elastic IP, known only after apply", "unknown", ["POL001"],
         "The rule's source address is unknown in the plan. The check cannot decide, so it fails closed.",
         lambda rs: rs.extend([res("aws_eip", "bastion", domain="vpc"),
                               rule("ingress", "service_from_bastion", "service", 22,
                                    cidr=Ref("aws_eip.bastion", "public_ip", "/32"))]))
    case("S14", "The worker may log in to the database as relay_service", "violation", [],
         "Specific, wildcard-free and wrong: the worker gains the service's privileges. No pattern sees intent.",
         set_attr("aws_iam_role_policy.worker_task", policy=pol(
             {"Effect": "Allow", "Action": ["rds-db:connect"],
              "Resource": [f"arn:aws:rds-db:{REGION}:{ACCOUNT}:dbuser:*/relay_worker",
                           f"arn:aws:rds-db:{REGION}:{ACCOUNT}:dbuser:*/relay_service"]},
             {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": MODEL_ARN})))
    case("S15", "Port 22 opened to 0.0.0.0/0 in the console after apply (drift)", "violation", [],
         "The change is not in any plan, so no plan check can see it. Posture management of the live account does.",
         lambda rs: None)
    case("S16", "The S3 gateway endpoint's policy is removed", "violation", ["POL004"],
         "AWS then applies its default policy: any principal may reach any bucket, including an attacker's.",
         set_attr("aws_vpc_endpoint.s3", policy=UNKNOWN))
    case("S17", "The database's public flag comes from a value known only after apply", "unknown", ["POL002"],
         "For example, read from a parameter created in the same change. The check cannot decide.",
         set_attr("aws_db_instance.relay", publicly_accessible=DERIVED))
    case("C01", "Control: tags set only through the provider's default tags", "control", [],
         "Every resource in the clean plan already relies on default_tags; this control also removes the "
         "per-resource Name tags. A check that reads `tags` instead of `tags_all` raises false alarms here.",
         drop_resource_tags)
    return cases


def destroy_variants() -> list[tuple[str, list[dict], dict]]:
    """(file stem, resources whose state the destroy plan deletes, default tags)."""
    def prepared(rs):
        find(rs, "aws_db_instance.relay")["attrs"]["deletion_protection"] = False
        return rs

    good = prepared(nonprod())
    protected = nonprod()
    shared = prepared(nonprod())
    shared.append(res("aws_db_instance", "shared_test", identifier="shared-test", engine="postgres",
                      instance_class="db.t4g.medium", storage_encrypted=True, deletion_protection=False,
                      skip_final_snapshot=True, tags={"env": "shared", "app": "test-data", "owner": "platform"}))
    no_snapshot = prepared(nonprod())
    find(no_snapshot, "aws_db_instance.relay")["attrs"]["skip_final_snapshot"] = True
    partial = without(prepared(nonprod()), "aws_nat_gateway.egress", "aws_eip.nat")
    return [("relay-nonprod", good, DEFAULT_TAGS), ("T1-protection-still-on", protected, DEFAULT_TAGS),
            ("T2-deletes-a-shared-database", shared, DEFAULT_TAGS), ("T3-no-final-snapshot", no_snapshot, DEFAULT_TAGS),
            ("T4-targeted-destroy-leaves-nat", partial, DEFAULT_TAGS)]


def tags(**kv):
    return [{"Key": k, "Value": v} for k, v in kv.items()]


# Shape of `aws resourcegroupstaggingapi get-resources --tag-filters Key=env,Values=nonprod`.
INVENTORIES = {
    "after-teardown": {"ResourceTagMappingList": [
        {"ResourceARN": f"arn:aws:rds:{REGION}:{ACCOUNT}:snapshot:relay-nonprod-final",
         "Tags": tags(app="relay", env="nonprod", owner="sam.o", **{"cost-center": "relay-eng"},
                      **{"data-class": "Internal"}, expires="2027-01-04")}]},
    "after-teardown-leftovers": {"ResourceTagMappingList": [
        {"ResourceARN": f"arn:aws:rds:{REGION}:{ACCOUNT}:snapshot:relay-nonprod-final",
         "Tags": tags(app="relay", env="nonprod", owner="sam.o", **{"cost-center": "relay-eng"})},
        {"ResourceARN": f"arn:aws:ec2:{REGION}:{ACCOUNT}:volume/vol-0handmade00000001",
         "Tags": tags(env="nonprod", owner="priya.n")},
        {"ResourceARN": f"arn:aws:ec2:{REGION}:{ACCOUNT}:elastic-ip/eipalloc-0handmade0000002",
         "Tags": tags(app="relay", env="nonprod")}]},
}

PRICES = {
    "price_table": "aws-us-east-1-2026-11",
    "as_of": "2026-11-10",
    "region": REGION,
    "currency": "USD",
    "hours_per_month": 730,
    "status": ("ASSUMPTIONS. On-demand list prices as the authors read them on the as-of date, Linux, no "
               "discounts, free tiers or credits. Verify every price on the AWS pricing pages before relying "
               "on a total; prices change and differ by region."),
    "hourly": {
        "ec2_instance": {"g5.48xlarge": 16.288, "g5.12xlarge": 5.672, "t4g.small": 0.0168, "m7g.large": 0.0816},
        "public_ipv4_address": 0.005,
        "fargate": {"ARM64": {"vcpu": 0.03238, "gb": 0.00356}, "X86_64": {"vcpu": 0.04048, "gb": 0.004445}},
        "rds_postgres_instance": {"db.t4g.small": 0.032, "db.t4g.medium": 0.065, "db.r6g.4xlarge": 1.798},
        "nat_gateway": 0.045,
        "vpc_interface_endpoint_per_az": 0.01,
        "network_firewall_endpoint": 0.395,
        "application_load_balancer": 0.0225,
    },
    "monthly": {
        "ebs_gp3_gb": 0.08,
        "rds_gp3_gb": 0.115,
        "secretsmanager_secret": 0.40,
        "kms_customer_managed_key": 1.00,
    },
    "rds_multi_az_factor": 2,
    "usage_based_not_estimated": {
        "nat_gateway_per_gb": 0.045, "vpc_endpoint_per_gb": 0.01, "alb_lcu_hour": 0.008,
        "cloudwatch_logs_ingest_per_gb": 0.50, "s3_standard_gb_month": 0.023, "ecr_storage_gb_month": 0.10,
        "bedrock_model_calls": "per input and output token; model-specific",
    },
}

RULES = {
    "POL001": ("high", "No ingress from the internet"),
    "POL002": ("high", "No public data endpoint"),
    "POL003": ("high", "No public compute or public model endpoint"),
    "POL004": ("high", "Private endpoints: model calls use one, and every endpoint has a restrictive policy"),
    "POL005": ("high", "Storage encrypted with a customer-managed key"),
    "POL006": ("medium", "Required tags present and valid"),
    "POL007": ("high", "No wildcard IAM in identity policies"),
    "POL008": ("high", "No long-lived credentials; CI federation pinned to one repository"),
    "POL009": ("high", "A budget with actual and forecast alerts, within the environment's ceiling"),
    "POL010": ("high", "No egress to the internet except allowlisted"),
    "POL011": ("medium", "Database protected: deletion protection, backups, final snapshot, standby"),
    "POL012": ("high", "Only approved regions and instance sizes"),
}

POLICY = {
    "policy_version": "cloud-policy-v1",
    "as_of_default": "2026-11-30",
    "rules": {k: {"severity": s, "title": t} for k, (s, t) in RULES.items()},
    "required_tags": ["app", "env", "owner", "cost-center", "data-class"],
    "allowed_env": ["prod", "nonprod", "lab", "sandbox"],
    "expires_required_for_env": ["lab", "sandbox"],
    "data_classes": ["Public", "Internal", "Confidential", "Restricted"],
    "max_data_class_outside_prod": "Internal",
    "allowed_regions": ["us-east-1", "us-west-2"],
    "allowed_instance_types": ["t4g.*", "m7g.large", "m7g.xlarge"],
    "allowed_db_classes": ["db.t4g.*", "db.m7g.large"],
    "egress_allowlist": [{"security_group": "aws_security_group.egress_proxy", "ports": [443],
                          "reason": "Allowlisting proxy for agent sandboxes (ADR-013)"}],
    "internet_route_tables": ["aws_route_table.egress", "aws_route_table.public"],
    "wildcard_resource_actions": ["ecr:GetAuthorizationToken"],
    "admin_managed_policies": ["arn:aws:iam::aws:policy/AdministratorAccess",
                               "arn:aws:iam::aws:policy/PowerUserAccess", "arn:aws:iam::aws:policy/IAMFullAccess"],
    "budget_ceiling_usd": {"nonprod": 500, "lab": 100, "sandbox": 100},
    "min_backup_retention_days": 7,
    "multi_az_required_for_env": ["nonprod", "prod"],
    "model_endpoint_services": ["bedrock-runtime"],
    "model_actions_prefix": "bedrock:Invoke",
    "oidc": {"host": "token.actions.githubusercontent.com", "audience": "sts.amazonaws.com"},
    "boundary_required_for_services": ["ecs-tasks.amazonaws.com"],
    "waivers": [{"id": "W-001", "rule": "POL007", "address": "aws_iam_role_policy.ci_apply",
                 "message": ("allows ec2:*, ecs:*, elasticloadbalancing:*, rds:*, secretsmanager:*, kms:*, logs:*, "
                             "ecr:*, budgets:*, s3:*, servicediscovery:*, route53:*"),
                 "owner": "sam.o",
                 "expires": "2027-02-26",
                 "reason": ("The apply role creates and deletes every resource type in this configuration, so its "
                            "service permissions are broad within the account. It is assumable only from the "
                            "protected nonprod environment after a reviewer approves. Its IAM permissions are not "
                            "covered by this waiver: it may create and pass only roles that carry the permissions "
                            "boundary, and cannot change the CI roles or the boundary. Narrow the service "
                            "permissions from CloudTrail's record of the actions it used in its first month.")}],
}


def overlay(base: dict, variant: dict) -> dict:
    """The difference between two plans, by resource address, as the lab's apply_overlay() reads it.

    A seeded case is small this way, and a learner can write a new one by hand. Applying the
    overlay to the clean plan rebuilds the variant's plan exactly (tests/test_data.py checks it).
    """
    def index(p):
        return ({r["address"]: r for r in p["resource_changes"]},
                {r["address"]: r for r in p["planned_values"]["root_module"]["resources"]},
                {r["address"]: r for r in p["configuration"]["root_module"]["resources"]})
    b_rc, b_pv, b_cf = index(base)
    v_rc, v_pv, v_cf = index(variant)
    upsert = []
    for addr, rc in v_rc.items():
        if rc != b_rc.get(addr) or v_pv[addr] != b_pv.get(addr) or v_cf.get(addr) != b_cf.get(addr):
            upsert.append({"address": addr, "resource_change": rc, "planned_value": v_pv[addr],
                           "configuration": v_cf.get(addr)})
    return {"format": "lab11.1-plan-overlay-v1", "remove": [a for a in b_rc if a not in v_rc], "upsert": upsert}


def write_json(path: Path, obj, compact: bool = False) -> None:
    """Plans are written on one line, as `tofu show -json` prints them; everything else is indented."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, separators=(",", ":")) if compact else json.dumps(obj, indent=1)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


def main() -> None:
    write_json(DATA / "policy.json", POLICY)
    write_json(DATA / "prices" / "aws-us-east-1-2026-11.json", PRICES)
    write_json(DATA / "plans" / "relay-nonprod.plan.json", plan(nonprod(), VARIABLES, DEFAULT_TAGS), compact=True)
    write_json(DATA / "plans" / "incident-lab.plan.json",
               plan(incident(), {"region": REGION}, {}, region_ref=False), compact=True)
    base = plan(nonprod(), VARIABLES, DEFAULT_TAGS)
    manifest = []
    for entry, rs, dtags in seeded():
        write_json(DATA / "seeded" / f"{entry['id']}.overlay.json", overlay(base, plan(rs, VARIABLES, dtags)),
                   compact=True)
        manifest.append(entry)
    write_json(DATA / "seeded" / "manifest.json", {"base": "plans/relay-nonprod.plan.json", "cases": manifest})
    for stem, rs, dtags in destroy_variants():
        write_json(DATA / "teardown" / f"{stem}.destroy.plan.json", destroy_plan(rs, VARIABLES, dtags),
                   compact=True)
    for stem, inv in INVENTORIES.items():
        write_json(DATA / "teardown" / f"inventory-{stem}.json", inv)
    write_json(DATA / "incident.json", {
        "composite": True,
        "environment": "plans/incident-lab.plan.json",
        "created_utc": "2026-11-06T16:15:00Z",
        "found_utc": "2026-11-09T10:15:00Z",
        "how_found": "an engineer opened the account's cost page on Monday morning",
        "counterfactual_budget_usd": 300,
    })


if __name__ == "__main__":
    main()

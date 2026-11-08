"""Policy as code over a plan: twelve rules, POL001-POL012 (data/policy.json).

Every check reads the plan's resources (cloudcheck.plan) and returns Findings. A check that
needs a value the plan does not know yet returns a "cannot check" finding instead of guessing:
the gate fails closed on it (exit status 2), as Chapter 5's drift gate did.

Scope, stated so that nobody assumes more: these rules read one plan. They do not see the live
account (drift, console changes), resources outside the configuration, values known only after
apply, or whether a correct-looking permission is the one the workload should have.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import date

from .plan import (Resource, configured, get, is_unknown, of_type, policy_document, reference, referring,
                   region, resources, statements, variable)

OPEN = {"0.0.0.0/0", "::/0"}
IDENTITY_POLICIES = {"aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_group_policy"}
ATTACHMENTS = {"aws_iam_role_policy_attachment", "aws_iam_user_policy_attachment", "aws_iam_group_policy_attachment",
               "aws_iam_policy_attachment"}


@dataclass(frozen=True)
class Finding:
    rule: str
    address: str
    message: str
    status: str = "fail"  # "fail", "cannot check" or "waived"


def fail(rule: str, r: Resource | str, message: str) -> Finding:
    return Finding(rule, r if isinstance(r, str) else r.address, message)


def cannot(rule: str, r: Resource, what: str) -> Finding:
    return Finding(rule, r.address, f"{what} is unknown until apply", "cannot check")


# ----------------------------------------------------------------- provided: POL001 and POL010

def _inline_rules(r: Resource, kind: str, rule_id: str) -> tuple[list[dict], list[Finding]]:
    """Inline ingress or egress blocks of a security group. Unknown and not configured means the
    provider computes them from separate rule resources, which are checked on their own."""
    if is_unknown(r, kind):
        return [], ([cannot(rule_id, r, kind)] if configured(r, kind) else [])
    return get(r, kind, default=[]), []


def _open(block: dict) -> list[str]:
    cidrs = set(block.get("cidr_blocks") or []) | set(block.get("ipv6_cidr_blocks") or [])
    return sorted(cidrs & OPEN)


def _ports(block: dict, proto_key: str) -> str:
    proto = block.get(proto_key)
    if proto in ("-1", "all"):
        return "all traffic"
    lo, hi = block.get("from_port"), block.get("to_port")
    return f"{proto} {lo}" if lo == hi else f"{proto} {lo}-{hi}"


def check_network(plan: dict, policy: dict) -> list[Finding]:
    """POL001 no ingress from the internet; POL010 no egress to the internet except allowlisted.

    Covers security-group rule resources (aws_vpc_security_group_*_rule and the older
    aws_security_group_rule), inline rules in aws_security_group and aws_default_security_group,
    and routes to 0.0.0.0/0 in aws_route_table and aws_route.
    """
    rs = resources(plan)
    allow = {a["security_group"]: set(a["ports"]) for a in policy["egress_allowlist"]}
    out: list[Finding] = []

    for r in of_type(rs, "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule"):
        rule_id = "POL001" if r.type.endswith("ingress_rule") else "POL010"
        if is_unknown(r, "cidr_ipv4") or is_unknown(r, "cidr_ipv6"):
            out.append(cannot(rule_id, r, "the source or destination address"))
            continue
        cidr = get(r, "cidr_ipv4") or get(r, "cidr_ipv6")
        if cidr not in OPEN:
            continue
        where = _ports(r.after, "ip_protocol")
        if rule_id == "POL001":
            out.append(fail(rule_id, r, f"ingress from {cidr} on {where}"))
        else:
            group = reference(r, "security_group_id")
            port = get(r, "from_port")
            if group in allow and port == get(r, "to_port") and port in allow[group]:
                continue
            out.append(fail(rule_id, r, f"egress to {cidr} on {where} from {group or 'an unknown group'}"))

    for r in of_type(rs, "aws_security_group_rule"):
        kind = get(r, "type")
        rule_id = "POL001" if kind == "ingress" else "POL010"
        if is_unknown(r, "cidr_blocks"):
            out.append(cannot(rule_id, r, "cidr_blocks"))
            continue
        for cidr in _open({"cidr_blocks": get(r, "cidr_blocks"), "ipv6_cidr_blocks": get(r, "ipv6_cidr_blocks")}):
            out.append(fail(rule_id, r, f"{kind} {'from' if kind == 'ingress' else 'to'} {cidr} on "
                                        f"{_ports(r.after, 'protocol')}"))

    for r in of_type(rs, "aws_security_group", "aws_default_security_group"):
        ingress, problems = _inline_rules(r, "ingress", "POL001")
        out += problems
        for block in ingress:
            for cidr in _open(block):
                out.append(fail("POL001", r, f"inline ingress from {cidr} on {_ports(block, 'protocol')}"))
        egress, problems = _inline_rules(r, "egress", "POL010")
        out += problems
        for block in egress:
            for cidr in _open(block):
                if r.address in allow and block.get("from_port") == block.get("to_port") \
                        and block.get("from_port") in allow[r.address]:
                    continue
                out.append(fail("POL010", r, f"inline egress to {cidr} on {_ports(block, 'protocol')}"))

    tables = set(policy["internet_route_tables"])
    for r in of_type(rs, "aws_route_table"):
        if is_unknown(r, "route") and not configured(r, "route"):
            continue  # no inline routes in the configuration
        for route in get(r, "route", default=[]) or []:
            if (route.get("cidr_block") in OPEN or route.get("ipv6_cidr_block") in OPEN) and r.address not in tables:
                out.append(fail("POL010", r, "route to the internet from a table not allowlisted"))
    for r in of_type(rs, "aws_route"):
        dest = get(r, "destination_cidr_block") or get(r, "destination_ipv6_cidr_block")
        if dest in OPEN and reference(r, "route_table_id") not in tables:
            out.append(fail("POL010", r, "route to the internet in a table not allowlisted"))
    return out


# ----------------------------------------------------------------- TODO 1: POL002-POL004

def _public_principal(statement: dict) -> bool:
    p = statement.get("Principal")
    return p == "*" or (isinstance(p, dict) and ("*" in (p.get("AWS") if isinstance(p.get("AWS"), list)
                                                       else [p.get("AWS")])))


def _grants_model_calls(rs: list[Resource], prefix: str) -> list[str]:
    """Identity policies that allow an action on the model API (prefix 'bedrock:')."""
    out = []
    for r in of_type(rs, *IDENTITY_POLICIES):
        doc = policy_document(r)
        if doc is None:
            continue
        for s in statements(doc):
            if s.get("Effect") == "Allow" and any(a.lower().startswith(prefix.lower().split(":")[0] + ":")
                                                 for a in s.get("Action", [])):
                out.append(r.address)
                break
    return out


def _unrestricted(statement: dict) -> bool:
    """An Allow statement open to any principal, for any action, on any resource, with no condition."""
    return (statement.get("Effect") == "Allow" and _public_principal(statement) and "*" in statement.get("Action", [])
            and "*" in statement.get("Resource", []) and not statement.get("Condition"))


def check_exposure(plan: dict, policy: dict) -> list[Finding]:
    """POL002 no public data endpoint; POL003 no public compute or model endpoint; POL004 private
    endpoints: model calls use one, and every endpoint has a restrictive policy.

    A flag that decides exposure and is unknown until apply gives a "cannot check" finding
    (cannot(rule, r, "<attribute>")), never a pass.
    POL002: an aws_db_instance with publicly_accessible true (unknown: cannot check); an
      aws_s3_bucket with no aws_s3_bucket_public_access_block (referring to it through `bucket`) that
      sets all four block/ignore/restrict flags to true; an aws_s3_bucket_policy with an Allow
      statement whose Principal is "*" (or {"AWS": "*"}) and no Condition.
    POL003: an aws_instance with associate_public_ip_address true; an aws_ecs_service with any
      network_configuration block's assign_public_ip true; an aws_lb with internal false. Each of
      these unknown: cannot check.
    POL004, model access: if any identity policy allows a 'bedrock:' action, the plan must have an
      Interface aws_vpc_endpoint whose service_name ends with one of policy["model_endpoint_services"]
      (".bedrock-runtime") with private_dns_enabled true ("(plan)" if there is none).
    POL004, every aws_vpc_endpoint: a policy that is unknown and not configured means AWS's default
      full-access policy ("endpoint uses the default full-access policy"); configured but unknown is
      "cannot check"; a known policy fails if any statement is _unrestricted
      ("endpoint policy allows any principal any action on any resource").
    One finding per problem, in the order above.
    """
    rs = resources(plan)
    out: list[Finding] = []
    for r in of_type(rs, "aws_db_instance"):
        if is_unknown(r, "publicly_accessible"):
            out.append(cannot("POL002", r, "publicly_accessible"))
        elif get(r, "publicly_accessible") is True:
            out.append(fail("POL002", r, "database is publicly accessible"))
    for r in of_type(rs, "aws_s3_bucket"):
        blocks = referring(rs, "aws_s3_bucket_public_access_block", "bucket", r.address)
        flags = ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")
        if not any(all(get(b, f) is True for f in flags) for b in blocks):
            out.append(fail("POL002", r, "bucket has no public access block with all four settings on"))
    for r in of_type(rs, "aws_s3_bucket_policy"):
        doc = policy_document(r)
        if doc is None:
            out.append(cannot("POL002", r, "the bucket policy"))
            continue
        if any(s.get("Effect") == "Allow" and _public_principal(s) and not s.get("Condition")
               for s in statements(doc)):
            out.append(fail("POL002", r, "bucket policy allows anyone"))

    for r in of_type(rs, "aws_instance"):
        if is_unknown(r, "associate_public_ip_address"):
            out.append(cannot("POL003", r, "associate_public_ip_address"))
        elif get(r, "associate_public_ip_address") is True:
            out.append(fail("POL003", r, "instance gets a public IP address"))
    for r in of_type(rs, "aws_ecs_service"):
        blocks = get(r, "network_configuration", default=[])
        if any(is_unknown(r, "network_configuration", i, "assign_public_ip") for i in range(len(blocks))):
            out.append(cannot("POL003", r, "assign_public_ip"))
        elif any(b.get("assign_public_ip") is True for b in blocks):
            out.append(fail("POL003", r, "tasks get public IP addresses"))
    for r in of_type(rs, "aws_lb"):
        if is_unknown(r, "internal"):
            out.append(cannot("POL003", r, "internal"))
        elif get(r, "internal") is False:
            out.append(fail("POL003", r, "load balancer is internet-facing"))

    if _grants_model_calls(rs, policy["model_actions_prefix"]):
        services = tuple("." + s for s in policy["model_endpoint_services"])
        endpoints = [r for r in of_type(rs, "aws_vpc_endpoint")
                     if str(get(r, "service_name", default="")).endswith(services)]
        if not endpoints:
            out.append(fail("POL004", "(plan)", "model calls are allowed but there is no private model endpoint"))
        for r in endpoints:
            if get(r, "vpc_endpoint_type") != "Interface":
                out.append(fail("POL004", r, "model endpoint is not an interface endpoint"))
            if get(r, "private_dns_enabled") is not True:
                out.append(fail("POL004", r, "private DNS is off, so clients resolve the public model endpoint"))
    for r in of_type(rs, "aws_vpc_endpoint"):
        doc = policy_document(r)
        if doc is None and is_unknown(r, "policy") and configured(r, "policy"):
            out.append(cannot("POL004", r, "the endpoint policy"))
        elif doc is None:
            out.append(fail("POL004", r, "endpoint uses the default full-access policy"))
        elif any(_unrestricted(s) for s in statements(doc)):
            out.append(fail("POL004", r, "endpoint policy allows any principal any action on any resource"))
    return out


# ----------------------------------------------------------------- TODO 2: POL005

def check_encryption(plan: dict, policy: dict) -> list[Finding]:
    """POL005 storage encrypted with a customer-managed key. One finding per resource and problem:

    - aws_db_instance: storage_encrypted must be true ("database storage is not encrypted").
    - aws_instance: every root_block_device block must have encrypted true ("root volume is not encrypted").
    - aws_ebs_volume: encrypted must be true ("volume is not encrypted").
    - aws_s3_bucket: some aws_s3_bucket_server_side_encryption_configuration referring to it (through
      `bucket`) must have a rule whose apply_server_side_encryption_by_default block has sse_algorithm
      "aws:kms" or "aws:kms:dsse" and kms_master_key_id set, known or unknown
      ("bucket is not encrypted with a customer-managed key").
    - aws_secretsmanager_secret and aws_cloudwatch_log_group: kms_key_id set, known or unknown
      ("uses the AWS managed key, not a customer-managed key").
    - aws_ecr_repository: an encryption_configuration block with encryption_type "KMS"
      ("repository is not encrypted with KMS").
    - aws_kms_key: enable_key_rotation true ("key rotation is off").
    "Set, known or unknown" means: a known non-null value, or unknown until apply.
    """
    rs = resources(plan)
    out: list[Finding] = []

    def is_set(r, attr):
        return get(r, attr) is not None or is_unknown(r, attr)

    for r in of_type(rs, "aws_db_instance"):
        if get(r, "storage_encrypted") is not True:
            out.append(fail("POL005", r, "database storage is not encrypted"))
    for r in of_type(rs, "aws_instance"):
        if any(b.get("encrypted") is not True for b in get(r, "root_block_device", default=[])):
            out.append(fail("POL005", r, "root volume is not encrypted"))
    for r in of_type(rs, "aws_ebs_volume"):
        if get(r, "encrypted") is not True:
            out.append(fail("POL005", r, "volume is not encrypted"))
    for r in of_type(rs, "aws_s3_bucket"):
        ok = False
        for c in referring(rs, "aws_s3_bucket_server_side_encryption_configuration", "bucket", r.address):
            for i, rule in enumerate(get(c, "rule", default=[])):
                for j, d in enumerate(rule.get("apply_server_side_encryption_by_default") or []):
                    key_set = d.get("kms_master_key_id") is not None or \
                        is_unknown(c, "rule", i, "apply_server_side_encryption_by_default", j, "kms_master_key_id")
                    ok = ok or (d.get("sse_algorithm") in ("aws:kms", "aws:kms:dsse") and key_set)
        if not ok:
            out.append(fail("POL005", r, "bucket is not encrypted with a customer-managed key"))
    for r in of_type(rs, "aws_secretsmanager_secret", "aws_cloudwatch_log_group"):
        if not is_set(r, "kms_key_id"):
            out.append(fail("POL005", r, "uses the AWS managed key, not a customer-managed key"))
    for r in of_type(rs, "aws_ecr_repository"):
        if not any(b.get("encryption_type") == "KMS" for b in get(r, "encryption_configuration", default=[])):
            out.append(fail("POL005", r, "repository is not encrypted with KMS"))
    for r in of_type(rs, "aws_kms_key"):
        if get(r, "enable_key_rotation") is not True:
            out.append(fail("POL005", r, "key rotation is off"))
    return out


# ----------------------------------------------------------------- TODO 3: POL006

def check_tags(plan: dict, policy: dict, as_of: date) -> list[Finding]:
    """POL006 required tags present and valid, on every taggable resource.

    A resource is taggable if `tags_all` appears in its after or after_unknown. Read tags_all,
    which includes the provider's default_tags; `tags` holds only the resource's own. If tags_all
    is unknown, return a "cannot check" finding. Otherwise, one finding per resource listing every
    problem found, in this order, joined with "; ":
      "missing <k1>, <k2>"                  required tags absent, in policy order
      "env '<v>' not allowed"               env not in policy["allowed_env"]
      "data-class '<v>' not allowed"        not one of policy["data_classes"]
      "data-class '<v>' not allowed in <env>"   above policy["max_data_class_outside_prod"] (by the
                                            order of data_classes) when env is not "prod"
      "no expires tag"                      env in policy["expires_required_for_env"] and no expires
      "expired on <date>"                   expires (ISO date) earlier than as_of
    """
    rs = resources(plan)
    out: list[Finding] = []
    classes = policy["data_classes"]
    ceiling = classes.index(policy["max_data_class_outside_prod"])
    for r in rs:
        if "tags_all" not in r.after and "tags_all" not in r.unknown:
            continue
        if is_unknown(r, "tags_all"):
            out.append(cannot("POL006", r, "tags_all"))
            continue
        tags = get(r, "tags_all", default={})
        problems = []
        missing = [k for k in policy["required_tags"] if k not in tags]
        if missing:
            problems.append("missing " + ", ".join(missing))
        env, dclass = tags.get("env"), tags.get("data-class")
        if env is not None and env not in policy["allowed_env"]:
            problems.append(f"env '{env}' not allowed")
        if dclass is not None and dclass not in classes:
            problems.append(f"data-class '{dclass}' not allowed")
        elif dclass is not None and env is not None and env != "prod" and classes.index(dclass) > ceiling:
            problems.append(f"data-class '{dclass}' not allowed in {env}")
        if env in policy["expires_required_for_env"] and "expires" not in tags:
            problems.append("no expires tag")
        if "expires" in tags and date.fromisoformat(tags["expires"]) < as_of:
            problems.append(f"expired on {tags['expires']}")
        if problems:
            out.append(fail("POL006", r, "; ".join(problems)))
    return out


# ----------------------------------------------------------------- TODO 4: POL007-POL008

def check_identity(plan: dict, policy: dict) -> list[Finding]:
    """POL007 no wildcard IAM in identity policies; POL008 no long-lived credentials, and CI
    federation pinned to one repository.

    POL007, for each identity policy resource (IDENTITY_POLICIES; its `policy` attribute; unknown
    gives "cannot check"), one finding per Allow statement that has any of:
      Actions "*" or "<service>:*"            -> "allows <a1>, <a2>, ..."    (every such action, in order)
      a NotAction                              -> "allows everything except <NotAction list>"
      a Resource "*" for an action not in policy["wildcard_resource_actions"]
                                               -> "allows <first action> on any resource"
    Check in that order and report only the first that applies to the statement. Also, for each
    policy attachment (ATTACHMENTS) whose policy_arn is in policy["admin_managed_policies"]:
      "attaches <policy name>" (the part after the last '/').
    And every aws_iam_role trusted by a service in policy["boundary_required_for_services"] (a
    Principal {"Service": ...} in its assume_role_policy) needs permissions_boundary set, known or
    unknown: "role has no permissions boundary".
    POL008:
      every aws_iam_user and aws_iam_access_key -> "long-lived credentials: an IAM user" / "... an access key"
      every aws_iam_role whose assume_role_policy has a statement with a Federated principal
      containing policy["oidc"]["host"]: the statement's StringEquals must set
      "<host>:aud" to policy["oidc"]["audience"] (else "OIDC audience not pinned"), and
      "<host>:sub" must appear under StringEquals with no "*" (else
      "OIDC subject not pinned to one repository and context").
    """
    rs = resources(plan)
    out: list[Finding] = []
    allowed_star = set(policy["wildcard_resource_actions"])
    for r in of_type(rs, *IDENTITY_POLICIES):
        doc = policy_document(r)
        if doc is None:
            out.append(cannot("POL007", r, "the policy document"))
            continue
        for s in statements(doc):
            if s.get("Effect") != "Allow":
                continue
            actions = s.get("Action", [])
            star = [a for a in actions if a == "*" or a.endswith(":*")]
            if star:
                out.append(fail("POL007", r, "allows " + ", ".join(star)))
            elif "NotAction" in s:
                out.append(fail("POL007", r, "allows everything except " + ", ".join(s["NotAction"])))
            elif "*" in s.get("Resource", []) and any(a not in allowed_star for a in actions):
                first = next(a for a in actions if a not in allowed_star)
                out.append(fail("POL007", r, f"allows {first} on any resource"))
    for r in of_type(rs, *ATTACHMENTS):
        arn = get(r, "policy_arn", default="")
        if arn in policy["admin_managed_policies"]:
            out.append(fail("POL007", r, f"attaches {arn.rsplit('/', 1)[-1]}"))

    bounded = set(policy.get("boundary_required_for_services", []))
    for r in of_type(rs, "aws_iam_role"):
        doc = policy_document(r, "assume_role_policy")
        services = set()
        for s in statements(doc) if doc else []:
            svc = (s.get("Principal") or {}).get("Service", []) if isinstance(s.get("Principal"), dict) else []
            services |= set(svc if isinstance(svc, list) else [svc])
        has_boundary = get(r, "permissions_boundary") is not None or is_unknown(r, "permissions_boundary")
        if services & bounded and not has_boundary:
            out.append(fail("POL007", r, "role has no permissions boundary"))

    for r in of_type(rs, "aws_iam_user"):
        out.append(fail("POL008", r, "long-lived credentials: an IAM user"))
    for r in of_type(rs, "aws_iam_access_key"):
        out.append(fail("POL008", r, "long-lived credentials: an access key"))
    host, audience = policy["oidc"]["host"], policy["oidc"]["audience"]
    for r in of_type(rs, "aws_iam_role"):
        doc = policy_document(r, "assume_role_policy")
        if doc is None:
            continue
        for s in statements(doc):
            fed = (s.get("Principal") or {}).get("Federated", "") if isinstance(s.get("Principal"), dict) else ""
            if host not in str(fed):
                continue
            equals = (s.get("Condition") or {}).get("StringEquals", {})
            if equals.get(f"{host}:aud") != audience:
                out.append(fail("POL008", r, "OIDC audience not pinned"))
            sub = equals.get(f"{host}:sub")
            if not sub or "*" in str(sub):
                out.append(fail("POL008", r, "OIDC subject not pinned to one repository and context"))
    return out


# ----------------------------------------------------------------- TODO 5: POL009, POL011, POL012

def check_guardrails(plan: dict, policy: dict) -> list[Finding]:
    """POL009 budget; POL011 database protection; POL012 regions and sizes.

    env is the plan's `env` variable (None if absent).
    POL009: budgets are aws_budgets_budget with budget_type "COST" and time_unit "MONTHLY". None ->
      one finding at "(plan)": "no monthly cost budget". Otherwise, for each budget: it needs a
      notification with notification_type "ACTUAL" and one with "FORECASTED", each with at least one
      subscriber (subscriber_email_addresses or subscriber_sns_topic_arns)
      ("budget lacks an actual or a forecast alert"). And if env has a ceiling in
      policy["budget_ceiling_usd"], at least one budget's float(limit_amount) must be at or under it
      ("no budget at or under the <env> ceiling of $<n>", at "(plan)").
    POL011, for each aws_db_instance, one finding per problem, in this order:
      "deletion protection is off"; "backups kept <n> days, fewer than <min>";
      "no final snapshot on delete" (skip_final_snapshot true); "no standby in a second zone"
      (multi_az not true, only when env is in policy["multi_az_required_for_env"]).
    POL012: the plan's region (cloudcheck.plan.region) must be in policy["allowed_regions"]
      (finding at "(plan)": "region <r> not allowed"); every aws_instance's instance_type must match a
      pattern in policy["allowed_instance_types"] (fnmatch) ("instance type <t> not allowed"); every
      aws_db_instance's instance_class a pattern in policy["allowed_db_classes"] ("database class <c> not allowed").
    """
    rs = resources(plan)
    env = variable(plan, "env")
    out: list[Finding] = []
    budgets = [r for r in of_type(rs, "aws_budgets_budget")
               if get(r, "budget_type") == "COST" and get(r, "time_unit") == "MONTHLY"]
    if not budgets:
        out.append(fail("POL009", "(plan)", "no monthly cost budget"))
    for b in budgets:
        kinds = {n.get("notification_type") for n in get(b, "notification", default=[])
                 if n.get("subscriber_email_addresses") or n.get("subscriber_sns_topic_arns")}
        if not {"ACTUAL", "FORECASTED"} <= kinds:
            out.append(fail("POL009", b, "budget lacks an actual or a forecast alert"))
    ceiling = policy["budget_ceiling_usd"].get(env) if env else None
    if budgets and ceiling is not None and not any(float(get(b, "limit_amount", default="inf")) <= ceiling
                                                   for b in budgets):
        out.append(fail("POL009", "(plan)", f"no budget at or under the {env} ceiling of ${ceiling}"))

    for r in of_type(rs, "aws_db_instance"):
        if get(r, "deletion_protection") is not True:
            out.append(fail("POL011", r, "deletion protection is off"))
        days = get(r, "backup_retention_period", default=0)
        if days < policy["min_backup_retention_days"]:
            out.append(fail("POL011", r, f"backups kept {days} days, fewer than {policy['min_backup_retention_days']}"))
        if get(r, "skip_final_snapshot") is True:
            out.append(fail("POL011", r, "no final snapshot on delete"))
        if env in policy["multi_az_required_for_env"] and get(r, "multi_az") is not True:
            out.append(fail("POL011", r, "no standby in a second zone"))

    reg = region(plan)
    if reg not in policy["allowed_regions"]:
        out.append(fail("POL012", "(plan)", f"region {reg} not allowed"))
    for r in of_type(rs, "aws_instance"):
        t = get(r, "instance_type", default="")
        if not any(fnmatch.fnmatchcase(t, p) for p in policy["allowed_instance_types"]):
            out.append(fail("POL012", r, f"instance type {t} not allowed"))
    for r in of_type(rs, "aws_db_instance"):
        c = get(r, "instance_class", default="")
        if not any(fnmatch.fnmatchcase(c, p) for p in policy["allowed_db_classes"]):
            out.append(fail("POL012", r, f"database class {c} not allowed"))
    return out


# ----------------------------------------------------------------- provided: run, waivers, gate

def apply_waivers(findings: list[Finding], policy: dict, as_of: date) -> list[Finding]:
    """A failing finding covered by an unexpired waiver becomes "waived". A waiver names the rule,
    the address and, if it has one, the exact message, so a new problem at the same address (another
    wildcard, say) is not waived silently. An expired waiver changes nothing except the message."""
    out = []
    for f in findings:
        w = next((w for w in policy.get("waivers", []) if w["rule"] == f.rule and w["address"] == f.address
                  and w.get("message", f.message) == f.message), None)
        if f.status == "fail" and w is not None:
            if as_of <= date.fromisoformat(w["expires"]):
                f = Finding(f.rule, f.address, f"{f.message} (waiver {w['id']}, owner {w['owner']}, "
                                               f"expires {w['expires']})", "waived")
            else:
                f = Finding(f.rule, f.address, f"{f.message} (waiver {w['id']} expired {w['expires']})")
        out.append(f)
    return out


def run_policy(plan: dict, policy: dict, as_of: date) -> list[Finding]:
    findings = (check_network(plan, policy) + check_exposure(plan, policy) + check_encryption(plan, policy)
                + check_tags(plan, policy, as_of) + check_identity(plan, policy) + check_guardrails(plan, policy))
    return sorted(apply_waivers(findings, policy, as_of), key=lambda f: (f.rule, f.address, f.message))


def gate_status(findings: list[Finding]) -> int:
    """0 pass; 1 at least one failing finding; 2 nothing failing, but something could not be checked."""
    if any(f.status == "fail" for f in findings):
        return 1
    if any(f.status == "cannot check" for f in findings):
        return 2
    return 0

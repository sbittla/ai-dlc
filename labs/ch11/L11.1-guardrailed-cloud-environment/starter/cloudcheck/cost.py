"""A cost estimate from the plan and a dated price table (data/prices/).

It answers one question: what does this environment cost per hour, and per month, just for
existing? It prices only what is billed by the hour or month whatever the traffic. Everything
billed by use (data processed, requests, log volume, storage that grows, model tokens) is listed
as "usage-based, not estimated" rather than guessed. The prices are assumptions to verify.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .plan import Resource, get, of_type, reference, resources

CATEGORIES = ("compute", "database", "network", "security", "storage")
USAGE_BASED = {
    "aws_s3_bucket": "storage and requests",
    "aws_cloudwatch_log_group": "log ingestion and storage",
    "aws_ecr_repository": "image storage",
    "aws_flow_log": "log delivery",
}


@dataclass(frozen=True)
class Line:
    address: str
    category: str
    hourly: float
    basis: str


@dataclass
class Estimate:
    lines: list[Line] = field(default_factory=list)
    usage: list[tuple[str, str]] = field(default_factory=list)  # (address, what is billed by use)
    unpriced: list[tuple[str, str]] = field(default_factory=list)  # (address, missing price key)
    hours_per_month: int = 730

    @property
    def hourly(self) -> float:
        return sum(line.hourly for line in self.lines)

    @property
    def monthly(self) -> float:
        return self.hourly * self.hours_per_month

    def by_category(self) -> dict[str, float]:
        return {c: sum(x.hourly for x in self.lines if x.category == c) for c in CATEGORIES}


def _task_size(rs: list[Resource], service: Resource) -> tuple[float, float, str] | None:
    target = reference(service, "task_definition")
    for t in of_type(rs, "aws_ecs_task_definition"):
        if t.address == target:
            arch = (get(t, "runtime_platform", default=[{}]) or [{}])[0].get("cpu_architecture", "X86_64")
            return int(get(t, "cpu")) / 1024, int(get(t, "memory")) / 1024, arch
    return None


def estimate(plan: dict, prices: dict) -> Estimate:
    """TODO 6. Price every resource that bills by the hour or month just for existing.

    Prices: prices["hourly"][...] are per hour; prices["monthly"][...] per month, converted with
    prices["hours_per_month"]. One Line per priced item, in plan order, with these categories:

      aws_ecs_service      compute   desired_count x (vCPU x fargate[arch]["vcpu"] + GB x fargate[arch]["gb"]),
                                     vCPU = cpu/1024 and GB = memory/1024 of the task definition the
                                     service refers to (use _task_size); arch from its runtime_platform
      aws_instance         compute   ec2_instance[instance_type]; plus a storage line for the root volumes
                                     (sum of volume_size x monthly ebs_gp3_gb / hours) at the same address;
                                     plus a network line public_ipv4_address if associate_public_ip_address
      aws_db_instance      database  rds_postgres_instance[instance_class] x f, plus allocated_storage x
                                     monthly rds_gp3_gb / hours x f, as one line, where f is
                                     prices["rds_multi_az_factor"] if multi_az else 1
      aws_vpc_endpoint     network   Interface only: len(subnet_ids) x vpc_interface_endpoint_per_az.
                                     Gateway endpoints cost nothing by the hour: no line.
      aws_nat_gateway      network   nat_gateway (and a usage entry: "data processed")
      aws_eip              network   public_ipv4_address
      aws_lb               network   application_load_balancer (and a usage entry: "load balancer capacity units")
      aws_networkfirewall_firewall network  len(subnet_mapping) x network_firewall_endpoint
      aws_secretsmanager_secret security  monthly secretsmanager_secret / hours
      aws_kms_key          security  monthly kms_customer_managed_key / hours

    Usage entries: every resource type in USAGE_BASED (with its text), plus any interface endpoint
    whose service_name ends with ".bedrock-runtime" ("model calls, per token"). A missing price key
    adds (address, key) to `unpriced` instead of a line. `basis` is free text saying how the line
    was computed; the tests do not read it.
    """
    raise NotImplementedError("TODO 6: estimate")


def hours_to_threshold(hourly: float, budget_usd: float, percent: float) -> float:
    """Hours of running at `hourly` before spend crosses `percent` of a budget (from zero)."""
    return budget_usd * percent / 100 / hourly

"""Monthly fixed cost of one workload on three providers, each under its own pricing model.

The comparison is only as good as its assumptions, which are all in data/: the workload's shape,
and dated price tables labelled as assumptions. Usage-based charges are left out on every side.
"""

from __future__ import annotations

import copy

CATEGORIES = ("containers", "database", "private_endpoints", "egress", "load_balancer", "secrets_keys")
SECONDS_PER_HOUR = 3600
HOURS_PER_WEEK = 168


def container_hours(workload: dict, c: dict) -> float:
    return c.get("hours", workload["hours_per_month"])


def monthly_cost(workload: dict, prices: dict, high_availability: bool | None = None) -> dict[str, float]:
    """TODO 2. The workload's fixed monthly cost on one provider, by category, plus "total".

    H = workload["hours_per_month"]; a container's hours are container_hours(workload, c).
    containers, by prices["containers"]["billing"]:
      "per_hour"               sum of count x hours x (vcpu x vcpu_hour + gib x gib_hour)
      "per_second"             sum of count x hours x 3600 x (vcpu x vcpu_second + gib x gib_second)
      "per_second_with_grant"  total vCPU-seconds and GiB-seconds over all containers, each reduced by its
                               free grant (free_vcpu_seconds, free_gib_seconds; never below 0), times its rate
    database: ha = workload["database"]["high_availability"] unless high_availability is given.
      With ha: class_hour x ha_factor x H + storage_gib x storage_gib_month x storage_ha_factor.
      Without: the "without_ha" class_hour if the table has one, else class_hour, x H, plus
      storage_gib x storage_gib_month.
    private_endpoints, by prices["private_endpoints"]["billing"]:
      "per_service_per_zone_hour"  services x zones x rate x H;  "per_service_hour"  services x rate x H;
      "none"  0
    egress: nat_gateways x nat_gateway_hour x H + public_ipv4 x public_ipv4_hour x H
    load_balancer: internal_load_balancer_hour x H if workload["internal_load_balancer"], else 0
    secrets_keys: secrets x secret_month + keys x key_month
    Return {category: dollars for each of CATEGORIES, "total": their sum}, unrounded.
    """
    raise NotImplementedError("TODO 2: monthly_cost")


def schedule(workload: dict, hours_per_week: float) -> dict:
    """TODO 3. A copy of the workload in which every container with "schedulable": true runs only
    `hours_per_week` hours a week: its "hours" become hours_per_month x hours_per_week / 168. Other
    containers and every other field are unchanged. The input is not modified."""
    raise NotImplementedError("TODO 3: schedule")

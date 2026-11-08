"""Hand-checkable tests for the mapping checker and the cost comparison."""

import pytest

from cloudmap.compare import monthly_cost, schedule
from cloudmap.mapping import check_mapping

DIMS = ["identity", "pricing"]


def row(concern, eq="close", diffs=(), aws="a", azure="z", gcp="g", verify=True):
    return {"concern": concern, "aws": aws, "azure": azure, "gcp": gcp, "equivalence": eq,
            "differences": [{"dimension": d, "note": "n"} for d in diffs], "verify": verify}


def test_a_clean_mapping_passes():
    m = {"dimensions": DIMS, "rows": [row("A", "partial", ["identity"]), row("B", "close", ["pricing"])]}
    assert check_mapping(m, ["A", "B"]) == []


def test_every_problem_in_order():
    m = {"dimensions": DIMS, "rows": [
        row("A", "partial"), row("A", "close", ["pricing"]), row("B", "same", gcp=" "),
        row("C", "close", ["cost"], verify=False)]}
    assert check_mapping(m, ["A", "B", "C", "D"]) == [
        "missing concern: D", "duplicate concern: A", "A: partial but no difference given",
        "B: no gcp service", "B: unknown equivalence 'same'", "C: unknown dimension 'cost'",
        "C: not marked for verification", "no difference recorded for identity"]


def tiny(billing_prices, containers, ha=True, endpoints=None, lb=False):
    workload = {"hours_per_month": 100, "containers": containers,
                "database": {"high_availability": ha, "storage_gib": 10},
                "private_endpoints": endpoints or {"services": 2, "zones": 2}, "nat_gateways": 1, "public_ipv4": 1,
                "internal_load_balancer": lb, "secrets": 2, "keys": 1}
    prices = {"containers": billing_prices,
              "database": {"class_hour": 0.1, "ha_factor": 2, "storage_gib_month": 0.2, "storage_ha_factor": 2,
                           "without_ha": {"class_hour": 0.05}},
              "private_endpoints": {"billing": "per_service_per_zone_hour", "rate": 0.01},
              "nat_gateway_hour": 0.04, "public_ipv4_hour": 0.005, "internal_load_balancer_hour": 0.02,
              "secret_month": 0.4, "key_month": 1.0}
    return workload, prices


ONE = [{"name": "s", "vcpu": 0.5, "gib": 1.0, "count": 2, "schedulable": True}]


def test_per_hour_billing_and_every_category():
    w, p = tiny({"billing": "per_hour", "vcpu_hour": 0.04, "gib_hour": 0.004}, ONE, lb=True)
    cost = {k: round(v, 4) for k, v in monthly_cost(w, p).items()}
    # containers 2 x 100 x (0.02 + 0.004) = 4.8; database 0.1 x 2 x 100 + 10 x 0.2 x 2 = 24
    # endpoints 2 x 2 x 0.01 x 100 = 4; egress 4 + 0.5 = 4.5; load balancer 2; secrets and keys 1.8
    assert cost == {"containers": 4.8, "database": 24.0, "private_endpoints": 4.0, "egress": 4.5,
                    "load_balancer": 2.0, "secrets_keys": 1.8, "total": 41.1}


def test_per_second_and_the_free_grant():
    w, p = tiny({"billing": "per_second", "vcpu_second": 0.00001, "gib_second": 0.000001}, ONE)
    assert round(monthly_cost(w, p)["containers"], 4) == 4.32  # 720,000 s x (0.5e-5 + 1e-6) ... x 2 tasks
    w, p = tiny({"billing": "per_second_with_grant", "vcpu_second": 0.00001, "gib_second": 0.000001,
                 "free_vcpu_seconds": 300000, "free_gib_seconds": 1000000}, ONE)
    # vCPU-s 360,000 - 300,000 = 60,000 -> 0.60; GiB-s 720,000 - 1,000,000 -> 0
    assert round(monthly_cost(w, p)["containers"], 4) == 0.6


def test_without_a_standby_and_other_endpoint_billing():
    w, p = tiny({"billing": "per_hour", "vcpu_hour": 0, "gib_hour": 0}, ONE, ha=False)
    assert round(monthly_cost(w, p)["database"], 4) == 7.0  # 0.05 x 100 + 10 x 0.2
    assert round(monthly_cost(w, p, high_availability=True)["database"], 4) == 24.0
    p["private_endpoints"] = {"billing": "per_service_hour", "rate": 0.01}
    assert round(monthly_cost(w, p)["private_endpoints"], 4) == 2.0
    p["private_endpoints"] = {"billing": "none", "rate": 0.0}
    assert monthly_cost(w, p)["private_endpoints"] == 0


def test_schedule_changes_only_schedulable_containers():
    w, _ = tiny({"billing": "per_hour"}, ONE + [{"name": "w", "vcpu": 1, "gib": 1, "count": 1, "schedulable": False}])
    s = schedule(w, 42)
    assert [c.get("hours") for c in s["containers"]] == [pytest.approx(25.0), None]
    assert "hours" not in w["containers"][0]

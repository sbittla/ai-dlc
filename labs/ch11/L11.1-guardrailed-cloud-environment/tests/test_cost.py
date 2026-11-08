"""The cost estimator on small plans with hand-computed answers (prices from data/prices/)."""

import pytest
from conftest import PRICES, mkplan, rc

from cloudcheck.cost import estimate, hours_to_threshold


def task(name, cpu, memory, arch="ARM64"):
    return rc("aws_ecs_task_definition", name, {"cpu": cpu, "memory": memory,
                                                "runtime_platform": [{"cpu_architecture": arch}]})


def service(name, count, td):
    return rc("aws_ecs_service", name, {"desired_count": count}, unknown={"task_definition": True},
              config={"task_definition": {"references": [f"{td}.arn", td]}})


def test_fargate_service_is_priced_from_its_task_definition():
    # 2 tasks x (0.5 vCPU x 0.03238 + 1 GB x 0.00356) = 0.0395 per hour
    p = mkplan(task("t", "512", "1024"), service("s", 2, "aws_ecs_task_definition.t"))
    est = estimate(p, PRICES)
    assert [(x.address, x.category, round(x.hourly, 6)) for x in est.lines] == [("aws_ecs_service.s", "compute", 0.0395)]


def test_x86_costs_more_than_arm():
    arm = estimate(mkplan(task("t", "1024", "2048"), service("s", 1, "aws_ecs_task_definition.t")), PRICES)
    x86 = estimate(mkplan(task("t", "1024", "2048", "X86_64"), service("s", 1, "aws_ecs_task_definition.t")), PRICES)
    assert (round(arm.hourly, 5), round(x86.hourly, 5)) == (0.0395, 0.04937)


def test_multi_az_database_doubles_instance_and_storage():
    # (0.032 + 20 x 0.115 / 730) x 2 = 0.070301 per hour
    p = mkplan(rc("aws_db_instance", "db", {"instance_class": "db.t4g.small", "allocated_storage": 20,
                                            "multi_az": True}))
    assert round(estimate(p, PRICES).hourly, 6) == 0.070301


def test_interface_endpoints_bill_per_zone_and_gateways_are_free():
    p = mkplan(rc("aws_vpc_endpoint", "logs", {"vpc_endpoint_type": "Interface", "subnet_ids": [None, None],
                                               "service_name": "com.amazonaws.us-east-1.logs"}),
               rc("aws_vpc_endpoint", "s3", {"vpc_endpoint_type": "Gateway", "service_name": "com.amazonaws.us-east-1.s3"}))
    est = estimate(p, PRICES)
    assert [(x.address, round(x.hourly, 4)) for x in est.lines] == [("aws_vpc_endpoint.logs", 0.02)]


def test_instance_with_volume_and_public_ip_gives_three_lines():
    p = mkplan(rc("aws_instance", "gpu", {"instance_type": "g5.48xlarge", "associate_public_ip_address": True,
                                          "root_block_device": [{"volume_size": 1000}]}))
    est = estimate(p, PRICES)
    assert [(x.category, round(x.hourly, 4)) for x in est.lines] == [("compute", 16.288), ("storage", 0.1096),
                                                                     ("network", 0.005)]


def test_usage_based_items_are_listed_not_priced():
    p = mkplan(rc("aws_s3_bucket", "b", {}), rc("aws_nat_gateway", "n", {}),
               rc("aws_vpc_endpoint", "m", {"vpc_endpoint_type": "Interface", "subnet_ids": [None],
                                            "service_name": "com.amazonaws.us-east-1.bedrock-runtime"}))
    est = estimate(p, PRICES)
    assert est.usage == [("aws_s3_bucket.b", "storage and requests"), ("aws_nat_gateway.n", "data processed"),
                         ("aws_vpc_endpoint.m", "model calls, per token")]
    assert round(est.hourly, 3) == 0.055


def test_a_missing_price_is_reported_not_guessed():
    p = mkplan(rc("aws_instance", "odd", {"instance_type": "x9.huge"}))
    est = estimate(p, PRICES)
    assert est.lines == [] and est.unpriced == [("aws_instance.odd", "x9.huge")]


def test_monthly_is_730_hours_and_threshold_hours():
    est = estimate(mkplan(rc("aws_kms_key", "k", {}), rc("aws_secretsmanager_secret", "s", {})), PRICES)
    assert round(est.monthly, 2) == 1.40
    assert hours_to_threshold(30.0, 300, 50) == pytest.approx(5.0)

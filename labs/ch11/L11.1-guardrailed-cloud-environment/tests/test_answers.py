"""Locks the arithmetic and the outcomes in book/answers/ch11-answers.md (Exercises 5-7)."""

import copy
import json
from datetime import date

from conftest import DATA_DIR, POLICY, PRICES

from cloudcheck.cost import estimate, hours_to_threshold
from cloudcheck.plan import load_plan
from cloudcheck.policy import gate_status, run_policy

NONPROD = load_plan(DATA_DIR / "plans" / "relay-nonprod.plan.json")
INCIDENT = load_plan(DATA_DIR / "plans" / "incident-lab.plan.json")
AS_OF = date(2026, 11, 30)


def test_exercise_5_firewall_instead_of_proxy():
    est = estimate(NONPROD, PRICES)
    proxy = next(x.hourly for x in est.lines if x.address == "aws_ecs_service.egress_proxy")
    firewall = PRICES["hourly"]["network_firewall_endpoint"]
    hourly = est.hourly - proxy + firewall
    assert (round(proxy, 6), firewall) == (0.009875, 0.395)
    assert (round(hourly, 4), round(hourly * 730, 2), round(100 * firewall / hourly, 1)) == (0.6891, 503.04, 57.3)
    assert round((hourly - est.hourly) * 730, 2) == 281.14


def test_exercise_6_alerts_that_arrive_late():
    hourly = estimate(INCIDENT, PRICES).hourly
    rows = [(p, round(hours_to_threshold(hourly, 300, p), 1), round(hours_to_threshold(hourly, 300, p) + 8, 1),
             round(hourly * (hours_to_threshold(hourly, 300, p) + 8), 2)) for p in (50, 80, 100)]
    assert rows == [(50, 4.3, 12.3, 427.46), (80, 6.9, 14.9, 517.46), (100, 8.7, 16.7, 577.46)]


def _with_change(address, mutate):
    plan = copy.deepcopy(NONPROD)
    rc = next(r for r in plan["resource_changes"] if r["address"] == address)
    mutate(rc["change"]["after"])
    return plan


def test_exercise_7_two_changes_one_caught():
    def open_alb(after):
        after["cidr_ipv4"] = "0.0.0.0/0"
    a = run_policy(_with_change("aws_vpc_security_group_ingress_rule.alb_https_vpn", open_alb), POLICY, AS_OF)
    failing = [(f.rule, f.message) for f in a if f.status == "fail"]
    assert failing == [("POL001", "ingress from 0.0.0.0/0 on tcp 443")] and gate_status(a) == 1

    def any_model(after):
        doc = json.loads(after["policy"])
        doc["Statement"][1]["Resource"] = "arn:aws:bedrock:us-east-1::foundation-model/*"
        after["policy"] = json.dumps(doc, separators=(",", ":"))
    b = run_policy(_with_change("aws_iam_role_policy.worker_task", any_model), POLICY, AS_OF)
    assert [f for f in b if f.status == "fail"] == [] and gate_status(b) == 0

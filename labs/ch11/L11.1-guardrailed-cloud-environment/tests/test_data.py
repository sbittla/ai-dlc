"""The data is reproducible, honest about what it is, and consistent with Relay's OpenTofu files."""

import importlib.util
import json
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, POLICY, PRICES, RELAY

INFRA = RELAY / "infra"
PLAN = json.loads((DATA_DIR / "plans" / "relay-nonprod.plan.json").read_text(encoding="utf-8"))


def generator():
    spec = importlib.util.spec_from_file_location("gen11", LAB_ROOT / "scripts" / "generate_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    script = (LAB_ROOT / "scripts" / "generate_data.py").read_text(encoding="utf-8")
    copy = tmp_path / "scripts" / "generate_data.py"
    copy.parent.mkdir()
    copy.write_text(script, encoding="utf-8")
    subprocess.run([sys.executable, str(copy)], check=True, capture_output=True)
    out = tmp_path / "data"
    after = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert after == before


def test_plans_say_they_were_generated_and_keep_the_documented_keys():
    for path in sorted((DATA_DIR / "plans").glob("*.json")) + sorted((DATA_DIR / "teardown").glob("*.plan.json")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        assert plan["terraform_version"] == "0.0.0-lab11.1-generated", path.name
        assert plan["format_version"] == "1.2"
        assert set(plan) == {"format_version", "terraform_version", "variables", "planned_values",
                             "resource_changes", "configuration", "timestamp", "applyable", "complete", "errored"}
        for r in plan["resource_changes"]:
            assert set(r["change"]) == {"actions", "before", "after", "after_unknown", "before_sensitive",
                                        "after_sensitive"}
            assert r["provider_name"] == "registry.opentofu.org/hashicorp/aws"


def test_each_overlay_rebuilds_its_variant_exactly():
    gen = generator()
    sys.path.insert(0, str(LAB_ROOT / "solution"))
    from cloudcheck.plan import apply_overlay
    base = gen.plan(gen.nonprod(), gen.VARIABLES, gen.DEFAULT_TAGS)
    for entry, rs, tags in gen.seeded():
        overlay = json.loads((DATA_DIR / "seeded" / f"{entry['id']}.overlay.json").read_text(encoding="utf-8"))
        rebuilt = apply_overlay(base, overlay)
        variant = gen.plan(rs, gen.VARIABLES, tags)
        key = lambda p: sorted(json.dumps(r, sort_keys=True) for r in p["resource_changes"])  # noqa: E731
        assert key(rebuilt) == key(variant), entry["id"]


def test_unknown_values_are_marked_as_a_real_plan_marks_them():
    rcs = {r["address"]: r["change"] for r in PLAN["resource_changes"]}
    db = rcs["aws_db_instance.relay"]
    assert db["after_unknown"]["address"] is True and "address" not in db["after"]
    assert db["after"]["publicly_accessible"] is False and db["after"]["storage_encrypted"] is True
    assert rcs["aws_ecs_task_definition.service"]["after_unknown"]["container_definitions"] is True
    svc = rcs["aws_ecs_service.service"]
    assert svc["after"]["network_configuration"][0]["subnets"] == [None, None]
    assert svc["after_unknown"]["network_configuration"][0]["subnets"] == [True, True]


def test_the_opentofu_files_declare_exactly_the_planned_resources():
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(INFRA.glob("*.tf")))
    declared = sorted(f"{t}.{n}" for t, n in re.findall(r'^resource "(\w+)" "(\w+)"', text, re.M))
    planned = sorted(r["address"] for r in PLAN["configuration"]["root_module"]["resources"])
    assert declared == planned
    assert len(planned) == 100


def test_tfvars_match_the_plan_variables():
    tfvars = (INFRA / "nonprod.tfvars").read_text(encoding="utf-8")
    values = dict(re.findall(r'^(\w+)\s*=\s*(.+)$', tfvars, re.M))
    for name, v in PLAN["variables"].items():
        assert json.loads(values[name]) == v["value"], name


def test_guardrails_and_policy_agree():
    regions = json.loads((INFRA / "org" / "scp-deny-regions.json").read_text(encoding="utf-8"))
    assert regions["Statement"][0]["Condition"]["StringNotEquals"]["aws:RequestedRegion"] == POLICY["allowed_regions"]
    sizes = {s["Sid"]: s for s in json.loads((INFRA / "org" / "scp-deny-instance-types.json")
                                             .read_text(encoding="utf-8"))["Statement"]}
    assert sizes["NonProductionComputeSizes"]["Condition"]["StringNotLike"]["ec2:InstanceType"] == \
        POLICY["allowed_instance_types"]
    assert sizes["NonProductionDatabaseSizes"]["Condition"]["StringNotLike"]["rds:DatabaseClass"] == \
        POLICY["allowed_db_classes"]
    assert len(list((INFRA / "org").glob("scp-*.json"))) == 4  # plus FullAWSAccess: within the limit of ten (five before 15 May 2026)
    # Each SCP within 10,240 characters (5,120 before 15 May 2026); whitespace counts when the API saves the file
    assert all(len(f.read_text(encoding="utf-8")) <= 10240 for f in (INFRA / "org").glob("scp-*.json"))
    assert len(regions["Statement"][0]["NotAction"]) == 43  # AWS's sample region-deny list, plus account:*


def test_every_endpoint_in_the_plan_has_a_known_policy():
    eps = [r for r in PLAN["resource_changes"] if r["type"] == "aws_vpc_endpoint"]
    assert len(eps) == 6 and all(isinstance(r["change"]["after"].get("policy"), str) for r in eps)


def test_the_one_allowlisted_egress_rule_is_the_proxy():
    assert [a["security_group"] for a in POLICY["egress_allowlist"]] == ["aws_security_group.egress_proxy"]
    rule = next(r for r in PLAN["configuration"]["root_module"]["resources"]
                if r["address"] == "aws_vpc_security_group_egress_rule.proxy_https_internet")
    assert rule["expressions"]["security_group_id"]["references"][1] == "aws_security_group.egress_proxy"


def test_prices_are_dated_assumptions():
    assert PRICES["as_of"] == "2026-11-10" and PRICES["status"].startswith("ASSUMPTIONS")
    assert PRICES["hours_per_month"] == 730


def test_seeded_manifest_is_complete():
    manifest = json.loads((DATA_DIR / "seeded" / "manifest.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in manifest["cases"]]
    assert ids == [f"S{n:02d}" for n in range(1, 18)] + ["C01"]
    assert all((DATA_DIR / "seeded" / f"{i}.overlay.json").is_file() for i in ids)

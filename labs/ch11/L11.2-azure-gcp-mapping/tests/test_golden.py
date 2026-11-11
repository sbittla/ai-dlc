"""Golden tests: every number Chapter 11 quotes from Lab 11.2, and the data's reproducibility."""

import json
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, MAPPING, PRICES, REQUIRED, WORKLOAD

from cloudmap.compare import monthly_cost, schedule
from cloudmap.mapping import check_mapping, differences_by_dimension


def totals(workload, ha=None):
    return {p: round(monthly_cost(workload, PRICES[p], ha)["total"], 2) for p in ("aws", "azure", "gcp")}


def test_the_mapping_passes_and_the_draft_does_not():
    assert check_mapping(MAPPING, REQUIRED) == []
    assert len(MAPPING["rows"]) == 16
    assert [sum(r["equivalence"] == k for r in MAPPING["rows"]) for k in ("close", "partial", "different")] == [8, 7, 1]
    assert differences_by_dimension(MAPPING) == {"identity": 3, "networking": 5, "quotas": 1, "pricing": 6,
                                                 "guardrails": 5, "data": 2}
    draft = json.loads((DATA_DIR / "mapping-draft.json").read_text(encoding="utf-8"))
    problems = check_mapping(draft, REQUIRED)
    assert len(problems) == 21 and sum(p.startswith("missing concern") for p in problems) == 11


def test_comparison_under_the_stated_assumptions():
    assert totals(WORKLOAD) == {"aws": 221.9, "azure": 450.34, "gcp": 196.94}
    aws, azure = monthly_cost(WORKLOAD, PRICES["aws"]), monthly_cost(WORKLOAD, PRICES["azure"])
    assert (round(aws["private_endpoints"], 2), round(azure["private_endpoints"], 2)) == (73.0, 36.5)
    assert round(100 * azure["database"] / azure["total"], 1) == 58.7
    assert round(azure["database"], 2) == 264.48 and round(aws["database"], 2) == 51.32


def test_without_a_standby_the_order_changes():
    assert totals(WORKLOAD, ha=False) == {"aws": 196.24, "azure": 203.27, "gcp": 144.23}


def test_working_hours_schedule():
    assert totals(schedule(WORKLOAD, 50)) == {"aws": 201.64, "azure": 394.96, "gcp": 156.33}
    saved = {p: monthly_cost(WORKLOAD, PRICES[p])["total"] - monthly_cost(schedule(WORKLOAD, 50), PRICES[p])["total"]
             for p in PRICES}
    assert {p: round(v, 2) for p, v in saved.items()} == {"aws": 20.25, "azure": 55.38, "gcp": 40.61}
    shares = {p: round(100 * saved[p] / monthly_cost(WORKLOAD, PRICES[p])["total"], 1) for p in PRICES}
    assert shares == {"aws": 9.1, "azure": 12.3, "gcp": 20.6}


def test_table_11_11_by_category():
    rows = {p: {k: round(v, 2) for k, v in monthly_cost(WORKLOAD, PRICES[p]).items()} for p in PRICES}
    assert rows["aws"] == {"containers": 43.25, "database": 51.32, "private_endpoints": 73.0, "egress": 36.5,
                           "load_balancer": 16.43, "secrets_keys": 1.4, "total": 221.9}
    assert rows["azure"] == {"containers": 112.86, "database": 264.48, "private_endpoints": 36.5, "egress": 36.5,
                             "load_balancer": 0.0, "secrets_keys": 0.0, "total": 450.34}
    assert rows["gcp"] == {"containers": 86.72, "database": 105.42, "private_endpoints": 0.0, "egress": 4.67,
                           "load_balancer": 0.0, "secrets_keys": 0.12, "total": 196.94}


def test_prices_are_dated_assumptions():
    for table in PRICES.values():
        assert table["as_of"] == "2026-11-10" and table["status"].startswith("ASSUMPTIONS")


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    script = (LAB_ROOT / "scripts" / "generate_data.py").read_text(encoding="utf-8")
    copy = tmp_path / "scripts" / "generate_data.py"
    copy.parent.mkdir()
    copy.write_text(script, encoding="utf-8")
    subprocess.run([sys.executable, str(copy)], check=True, capture_output=True)
    out = tmp_path / "data"
    assert {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()} == before

"""The provided probes run Relay 4.26.0's real controls. These pass from the start.

Each probe must stop its attack class and let its benign case through. A probe that passes for the wrong reason
is the risk, so two checks below run a probe against a configuration where it MUST fail.
"""

import json

import pytest

from conftest import DATA_DIR
from redteam import probes

CLASSES = {c["id"]: c for c in json.loads((DATA_DIR / "classes.json").read_text(encoding="utf-8"))["classes"]}


@pytest.mark.parametrize("control, cid", [
    ("render", "C01"), ("render", "C03"), ("output_marking", "C02"), ("output_marking", "C04"),
    ("tool_scope", "C05"), ("approval", "C06"), ("delivery_binding", "C08"), ("egress", "C10"),
    ("egress", "C11"), ("memory_trust", "C12"), ("memory_review", "C13"), ("recall_taint", "C12"),
    ("judge_isolation", "C14"),
])
def test_each_blocking_probe_stops_its_class_and_allows_the_benign_case(control, cid):
    verdict = probes.PROBES[control](CLASSES[cid])
    assert verdict.blocks and verdict.allows_benign, verdict.evidence


def test_marking_works_but_never_counts_as_stopping_an_effect():
    verdict = probes.probe_marking(CLASSES["C01"])
    assert verdict.allows_benign and not verdict.blocks


def test_the_domain_only_allowlist_lets_an_attacker_path_on_an_allowlisted_host_through():
    assert not probes.probe_egress_domain_only(CLASSES["C10"]).blocks   # api.github.com, attacker's repository
    assert probes.probe_egress_domain_only(CLASSES["C11"]).blocks       # a host not on the list at all


def test_the_egress_probe_reads_the_committed_lists_not_a_copy(monkeypatch, tmp_path):
    for name in ("allowlist.txt", "content-hosts.txt"):
        (tmp_path / name).write_text((probes.PROXY / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "content-urls.txt").write_text("^https://api\\.github\\.com/\n", encoding="utf-8")  # too wide
    monkeypatch.setattr(probes, "PROXY", tmp_path)
    assert not probes.probe_egress(CLASSES["C10"]).blocks

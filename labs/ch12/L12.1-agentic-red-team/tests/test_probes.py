"""The provided probes run Relay 4.26.0's controls on its own artefacts. These pass from the start.

A probe that cannot be made to fail is broken (Chapter 12). The second half of this file breaks each control,
or the artefact it reads, and checks that its probe then fails.
"""

import json

import pytest

from conftest import DATA_DIR
from redteam import judge, probes

CLASSES = {c["id"]: c for c in json.loads((DATA_DIR / "classes.json").read_text(encoding="utf-8"))["classes"]}


@pytest.mark.parametrize("control, cid", [
    ("render", "C01"), ("render", "C03"), ("output_constraint", "C02"), ("output_constraint", "C04"),
    ("tool_allowlist", "C05"), ("approval", "C06"), ("platform_permissions", "C07"),
    ("delivery_binding", "C08"), ("tool_allowlist", "C09"), ("egress", "C10"), ("egress", "C11"),
    ("memory_review", "C12"), ("approval", "C13"),
])
def test_each_blocking_probe_stops_every_variant_and_allows_the_legitimate_case(control, cid):
    verdict = probes.PROBES[control](CLASSES[cid])
    assert verdict.blocks and verdict.allows_benign, verdict.evidence


@pytest.mark.parametrize("control, cid", [("marking", "C01"), ("memory_trust", "C12"), ("judge_isolation", "C14")])
def test_mitigating_probes_show_the_mechanism_but_never_block(control, cid):
    verdict = probes.PROBES[control](CLASSES[cid])
    assert verdict.allows_benign and not verdict.blocks


def test_the_domain_only_allowlist_lets_attacker_paths_and_mismatched_names_through():
    verdict = probes.probe_egress_domain_only(CLASSES["C10"])
    assert not verdict.blocks and "sni-mismatch" in verdict.evidence


# --- each probe can fail ---------------------------------------------------------------------------------

def test_egress_probe_fails_on_a_widened_url_list(monkeypatch, tmp_path):
    for name in ("allowlist.txt", "content-hosts.txt", "splice-hosts.txt", "squid.conf"):
        (tmp_path / name).write_text((probes.PROXY / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "content-urls.txt").write_text("^https://api\\.github\\.com/\n", encoding="utf-8")
    monkeypatch.setattr(probes, "PROXY", tmp_path)
    assert not probes.probe_egress(CLASSES["C10"]).blocks


def test_egress_probe_fails_without_terminate_or_strict_host_checking(monkeypatch, tmp_path):
    for name in ("allowlist.txt", "content-hosts.txt", "splice-hosts.txt", "content-urls.txt"):
        (tmp_path / name).write_text((probes.PROXY / name).read_text(encoding="utf-8"), encoding="utf-8")
    conf = (probes.PROXY / "squid.conf").read_text(encoding="utf-8")
    (tmp_path / "squid.conf").write_text(conf.replace("ssl_bump terminate all", "ssl_bump splice all")
                                         .replace("host_verify_strict on", ""), encoding="utf-8")
    monkeypatch.setattr(probes, "PROXY", tmp_path)
    verdict = probes.probe_egress(CLASSES["C11"])
    assert not verdict.blocks and "sni-mismatch" in verdict.evidence and "host-header-fronting" in verdict.evidence


def test_judge_isolation_probe_fails_when_isolation_is_removed(monkeypatch):
    monkeypatch.setattr(probes, "isolate", lambda answer: answer)
    assert not probes.probe_judge_isolation(CLASSES["C14"]).allows_benign
    assert judge.simulated_judge("label=access", "access", isolator=judge.isolate) == "pass"
    assert judge.simulated_judge("label=billing", "access", isolator=judge.isolate) == "fail"


def test_output_constraint_probe_fails_on_a_filter_that_only_knows_https(monkeypatch):
    monkeypatch.setattr(probes, "parse_summary",
                        lambda text: (None, "address") if "https://" in text else (text, None))
    verdict = probes.probe_output_constraint(CLASSES["C03"])
    assert not verdict.blocks and "reference-definition" in verdict.evidence


def test_run_taint_probe_fails_if_the_helper_reads_are_not_marked_untrusted(monkeypatch):
    import dataclasses
    tools = dict(probes.HELPER_TOOLS)
    tools["read_file"] = dataclasses.replace(tools["read_file"], untrusted_result=False)
    monkeypatch.setattr(probes, "HELPER_TOOLS", tools)
    assert not probes.probe_run_taint(CLASSES["C05"]).blocks


def test_platform_probe_fails_if_the_app_gains_workflow_permission(monkeypatch, tmp_path):
    gov = tmp_path / "governance"
    gov.mkdir()
    agents = json.loads((probes.GOVERNANCE / "agents.json").read_text(encoding="utf-8"))
    agents["github_apps"]["relay-spec-to-pr"]["installation_permissions"]["workflows"] = "write"
    (gov / "agents.json").write_text(json.dumps(agents), encoding="utf-8")
    (gov / "branch-protection.json").write_text(
        (probes.GOVERNANCE / "branch-protection.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(probes, "GOVERNANCE", gov)
    assert not probes.probe_platform_permissions(CLASSES["C05"]).blocks


def _proxy_copy(monkeypatch, tmp_path, conf):
    for name in ("allowlist.txt", "content-hosts.txt", "splice-hosts.txt", "content-urls.txt"):
        (tmp_path / name).write_text((probes.PROXY / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "squid.conf").write_text(conf, encoding="utf-8")
    monkeypatch.setattr(probes, "PROXY", tmp_path)


def test_splice_all_in_place_of_terminate_alone_makes_the_probe_fail(monkeypatch, tmp_path):
    conf = (probes.PROXY / "squid.conf").read_text(encoding="utf-8")
    _proxy_copy(monkeypatch, tmp_path, conf.replace("ssl_bump terminate all", "ssl_bump splice all"))
    verdict = probes.probe_egress(CLASSES["C11"])  # host_verify_strict stays on: it does not save a spliced tunnel
    assert not verdict.blocks and "sni-mismatch" in verdict.evidence


def test_splicing_by_server_name_alone_makes_the_probe_fail(monkeypatch, tmp_path):
    conf = (probes.PROXY / "squid.conf").read_text(encoding="utf-8")
    _proxy_copy(monkeypatch, tmp_path, conf.replace("ssl_bump splice splice_sni splice_dst",
                                                    "ssl_bump splice splice_sni"))
    verdict = probes.probe_egress(CLASSES["C10"])
    assert not verdict.blocks and "content-connect-spliced-name" in verdict.evidence


def test_egress_probe_reads_directives_not_substrings(monkeypatch, tmp_path):
    """A commented-out terminate rule followed by splice-all must make the probe fail."""
    for name in ("allowlist.txt", "content-hosts.txt", "splice-hosts.txt", "content-urls.txt"):
        (tmp_path / name).write_text((probes.PROXY / name).read_text(encoding="utf-8"), encoding="utf-8")
    conf = (probes.PROXY / "squid.conf").read_text(encoding="utf-8")
    conf = conf.replace("ssl_bump terminate all", "# ssl_bump terminate all\nssl_bump splice all")
    conf = conf.replace("host_verify_strict on", "# host_verify_strict on")
    (tmp_path / "squid.conf").write_text(conf, encoding="utf-8")
    monkeypatch.setattr(probes, "PROXY", tmp_path)
    assert not probes.probe_egress(CLASSES["C11"]).blocks

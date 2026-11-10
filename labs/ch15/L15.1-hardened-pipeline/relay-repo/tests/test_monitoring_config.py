"""The deployed monitoring configuration agrees with the tested code (4.27.0, ADR-036 to ADR-038). Read as text: the
collector files are YAML, and Relay has no YAML parser, so the checks are line-based and exact."""

import json
import re
from pathlib import Path

from relay.telemetry import semconv

ROOT = Path(__file__).resolve().parent.parent
SIDECAR = (ROOT / "infra/monitoring/collector-sidecar.yaml").read_text(encoding="utf-8")
GATEWAY = (ROOT / "infra/monitoring/collector-gateway.yaml").read_text(encoding="utf-8")
ROUTING = json.loads((ROOT / "infra/monitoring/routing.json").read_text(encoding="utf-8"))


def allowed_keys_in(text: str) -> set[str]:
    block = text.split("allowed_keys:", 1)[1].split("blocked_values:", 1)[0]
    return set(re.findall(r"^\s+- ([a-z0-9_.]+)\s*$", block, flags=re.M))


def test_the_collector_allowlist_is_relays_allowlist():
    assert allowed_keys_in(SIDECAR) == set(semconv.ALLOWED)
    assert "allow_all_keys: false" in SIDECAR


def test_the_collector_deletes_every_content_key_again():
    deleted = set(re.findall(r"\{key: ([a-z0-9_.]+), action: delete\}", SIDECAR))
    assert set(semconv.CONTENT_KEYS) - {"gen_ai.tool.definitions"} <= deleted
    assert "http\\\\.request\\\\.header" in SIDECAR


def test_every_pipeline_in_the_sidecar_redacts_except_the_audit_trail():
    pattern = r"^    ([a-z/]+):\n      receivers: \[(.*)\]\n      processors: \[(.*)\]"
    pipelines = re.findall(pattern, SIDECAR, flags=re.M)
    assert {p[0] for p in pipelines} == {"traces", "metrics", "logs", "logs/audit"}
    for name, receivers, processors in pipelines:
        assert ("redaction" in processors) is (name != "logs/audit"), name


def test_retention_and_destinations():
    assert "/relay/nonprod/telemetry" in GATEWAY and "/relay/nonprod/agent-audit" in GATEWAY
    assert "0.0.0.0:4319" in GATEWAY and "logs/audit" in GATEWAY


def test_paging_follows_the_on_call_policy():
    for name in ("platform-oncall", "security-oncall"):
        steps = ROUTING["receivers"][name]["escalation"]
        assert [(s["after_minutes"], s["to"]) for s in steps] == [(10, "secondary-oncall"), (20, "engineering-manager")]
    assert ROUTING["receivers"]["security-oncall"]["notify"] == {"security-lead": 60}


def test_every_detection_rule_is_routed():
    rules = json.loads((ROOT / "infra/detection/rules.json").read_text(encoding="utf-8"))["rules"]
    assert {r["id"] for r in rules} <= set(ROUTING["routes"]["by_rule"])
    assert ROUTING["routes"]["by_rule"]["DR-004"] == ["security-lead"]

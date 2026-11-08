"""Contract tests: the engine's documents against specs/001-escalation-rules/contracts/.

Spec: ESC-SPEC-1
Spec version: 1.1.0
"""

import dataclasses
import re
from datetime import timedelta, timezone

import pytest
import json

from escalation_fixtures import (ADMIN, MEMBER, ROTTERDAM, SCHEMA, SPEC_DIR, TASK, USERS, default_rule, minutes,
                                 p1_state, p2_rule)

from relay import escalation
from relay.escalation import model, rule_from_document, to_document, to_rule_document, validate, validate_rule
from relay.escalation.delivery import escalation_email, escalation_event, utc_minute
from relay.escalation.hours import ZONES
from relay.escalation.model import RuleRejected


def check(document, name):
    return validate(document, {"$ref": f"#/$defs/{name}"}, SCHEMA)


def test_contract_spec_and_package_share_one_version():
    spec_version = re.search(r"^Version: (\S+)$", (SPEC_DIR / "spec.md").read_text(encoding="utf-8"), re.M)
    assert SCHEMA["x-spec-version"] == escalation.SPEC_VERSION == spec_version.group(1)
    assert SCHEMA["$defs"]["Evaluation"]["properties"]["spec_version"]["const"] == escalation.SPEC_VERSION
    assert SCHEMA["$defs"]["WebhookEvent"]["properties"]["spec_version"]["const"] == escalation.SPEC_VERSION
    api = json.loads((SPEC_DIR / "contracts" / "escalation-api.openapi.json").read_text(encoding="utf-8"))
    assert api["info"]["x-spec-version"] == api["info"]["version"] == escalation.SPEC_VERSION


@pytest.mark.parametrize("name", ["Rule", "Step", "BusinessHours", "Evaluation", "StepDecision", "Rejection",
                                  "EmailMessage", "WebhookEvent"])
def test_contract_fields_equal_dataclass_fields(name):
    fields = [f.name for f in dataclasses.fields(getattr(model, name))]
    assert fields == list(SCHEMA["$defs"][name]["properties"])


def test_enums_equal_the_constants_they_name():
    for definition in SCHEMA["$defs"].values():
        for prop in definition["properties"].values():
            if "x-relay-constant" in prop:
                assert tuple(prop["enum"]) == getattr(model, prop["x-relay-constant"])


def test_documents_the_slice_produces_conform():
    assert check(to_document(default_rule()), "Rule") == []
    for at in (5, 10, 20, 25):
        result = escalation.evaluate(default_rule(), TASK, p1_state(), minutes(at))
        assert check(to_document(result), "Evaluation") == []
    with pytest.raises(RuleRejected) as info:
        validate_rule(default_rule(), MEMBER, ROTTERDAM, USERS)
    assert check(to_document(info.value.rejection), "Rejection") == []
    assert validate_rule(default_rule(), ADMIN, ROTTERDAM, USERS)  # oracle: predicate - accepted, not refused


def test_rule_documents_round_trip_and_conform():
    for rule in (default_rule(), p2_rule()):
        document = to_rule_document(rule)
        assert check(document, "Rule") == []
        assert rule_from_document(document) == rule
    assert "business_hours" not in to_rule_document(default_rule())  # optional fields are left out, not null


def test_delivery_documents_conform():
    from relay.escalation import StepDecision
    decision = StepDecision(1, (5, 2), minutes(10))
    link = "https://relay.example/ws-demo/projects/10/tasks/7"
    email = escalation_email(decision, 5, default_rule(), ROTTERDAM, 7, link, minutes(0), minutes(10))
    event = escalation_event(decision, default_rule(), ROTTERDAM, 7, link, minutes(0), minutes(10))
    assert check(to_document(email), "EmailMessage") == []
    assert check(to_document(event), "WebhookEvent") == []


def test_zone_enum_equals_the_zone_table():
    assert tuple(ZONES) == model.ZONE_NAMES


def test_contract_refuses_documents_from_other_designs():
    seconds = {"rule_id": "R1", "project_id": 10, "priority": "P1",
               "steps": [{"number": 1, "delay_seconds": 600, "targets": [5]}]}
    assert check(seconds, "Rule") == ["$.steps[0]: missing required field 'delay_minutes'",
                                      "$.steps[0]: field 'delay_seconds' is not in the contract"]
    leaky = to_document(escalation.evaluate(default_rule(), TASK, p1_state(), minutes(10)))
    leaky["task_title"] = TASK.title
    assert check(leaky, "Evaluation") == ["$: field 'task_title' is not in the contract"]


def test_validator_fails_closed_on_keywords_it_does_not_implement():
    with pytest.raises(ValueError, match="not implemented"):
        validate("ops@example.com", {"type": "string", "format": "email"})
    with pytest.raises(ValueError, match="points to no definition"):
        validate({}, {"$ref": "#/$defs/Missing"})


def test_validator_refuses_unsupported_keywords_a_document_never_reaches():
    with pytest.raises(ValueError, match="not implemented"):
        validate({}, {"type": "object", "properties": {"a": {"type": "string", "format": "email"}}})


def test_validator_refuses_keywords_beside_a_ref():
    schema = {"$defs": {"X": {"type": "integer"}}, "properties": {"n": {"$ref": "#/$defs/X", "maximum": 3}}}
    with pytest.raises(ValueError, match="beside"):
        validate({"n": 9}, schema)


def test_enum_and_const_compare_types_as_well_as_values():
    assert validate(1, {"enum": [True]}) == ["$: 1 is not one of [True]"]
    assert validate(True, {"const": 1}) == ["$: must be 1"]
    assert validate(False, {"enum": [0, 1]}) != [] and validate(1, {"enum": [0, 1]}) == []


def test_message_times_must_be_utc():
    assert utc_minute(minutes(0)) == "2026-11-24 02:30 UTC"
    with pytest.raises(ValueError):
        utc_minute(minutes(0).astimezone(timezone(timedelta(hours=1))))

"""Contract tests for the routes: the OpenAPI description against the service (ADR-009, spec Contracts).

Spec: ESC-SPEC-1
Spec version: 1.1.0

The description is the contract callers build against. These tests fail if a
route exists that it does not describe, if it describes a route the service
does not have, if a status code the service returns is undocumented, or if a
response body does not match the JSON Schema definition it references.
"""

import json
import re
from pathlib import Path

import pytest
from service_helpers import MATRIX, ONE_RULE, RULE, RULES, TASK, call, make_app

from relay.escalation import validate
from relay.service.escalation_routes import ROUTES

CONTRACTS = Path(__file__).resolve().parents[1] / "specs" / "001-escalation-rules" / "contracts"
API = json.loads((CONTRACTS / "escalation-api.openapi.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((CONTRACTS / "escalation-rules.schema.json").read_text(encoding="utf-8"))


def operation(method, template):
    return API["paths"][template][method.lower()]


def body_schema(response):
    return response["content"]["application/json"]["schema"]


def check(instance, schema):
    """Validate against an OpenAPI schema whose $refs point into the JSON Schema file or to components."""
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("escalation-rules.schema.json#/$defs/"):
            return validate(instance, {"$ref": "#" + ref.split("#", 1)[1]}, SCHEMA)
        return check(instance, API["components"]["schemas"][ref.rsplit("/", 1)[1]])
    if schema.get("properties", {}).get("rules"):
        assert set(instance) == {"rules"}
        return [e for r in instance["rules"] for e in validate(r, {"$ref": "#/$defs/Rule"}, SCHEMA)]
    return validate(instance, schema)


def test_the_description_names_exactly_the_routes_the_service_has():
    described = {(m.upper(), path) for path, ops in API["paths"].items() for m in ops}
    assert described == set(ROUTES)


def test_every_reference_into_the_json_schema_resolves():
    refs = set(re.findall(r'"\$ref": "escalation-rules\.schema\.json#/\$defs/(\w+)"', json.dumps(API)))
    assert refs == {"Rule", "Rejection", "RuleDeleted"} and refs <= set(SCHEMA["$defs"])  # RuleDeleted: 1.2.0


@pytest.mark.parametrize("template, method, path, token, body, status, why", MATRIX,
                         ids=[f"{m[1]} {m[0]}: {m[6]}" for m in MATRIX])
def test_every_refusal_the_service_returns_is_documented(template, method, path, token, body, status, why):
    if status == 405:
        assert method.lower() not in API["paths"][template]       # no such operation is described
    else:
        assert str(status) in operation(method, template)["responses"], why


def test_success_responses_match_their_schemas():
    app, _ = make_app()
    cases = [
        ("PUT", "/v1/projects/{pid}/escalation-rules/{rid}", ONE_RULE, "demo-admin", RULE, 201),
        ("PUT", "/v1/projects/{pid}/escalation-rules/{rid}", ONE_RULE, "demo-admin", RULE, 200),
        ("GET", "/v1/projects/{pid}/escalation-rules", RULES, "demo-member", None, 200),
        ("GET", "/v1/projects/{pid}/escalation-rules/{rid}", ONE_RULE, "demo-member", None, 200),
        ("POST", "/v1/projects/{pid}/tasks/{tid}/priority", TASK + "/priority", "demo-member", {"priority": "P1"}, 200),
        ("POST", "/v1/projects/{pid}/tasks/{tid}/acknowledge", TASK + "/acknowledge", "demo-guest", None, 200),
        ("GET", "/v1/projects/{pid}/tasks/{tid}/escalation", TASK + "/escalation", "demo-guest", None, 200),
    ]
    for method, template, path, token, body, expected in cases:
        status, _, payload = call(app, method, path, token, body)
        assert status == expected, (method, path)
        assert check(payload, body_schema(operation(method, template)["responses"][str(status)])) == [], path


def test_a_refusal_by_validate_rule_is_a_rejection_document():
    app, _ = make_app()
    bad = dict(RULE, steps=[{"number": 1, "delay_minutes": 10, "targets": [99]}])
    status, _, payload = call(app, "PUT", ONE_RULE, "demo-admin", bad)
    schema = body_schema(operation("PUT", "/v1/projects/{pid}/escalation-rules/{rid}")["responses"]["422"])
    assert status == 422 and check(payload, schema) == []

"""The delete route (spec ESC-SPEC-1 1.2.0, B7 and B8; ADR-016). Task T24.

Spec: ESC-SPEC-1
Spec version: 1.2.0

The demo workspace has one Owner (user 1) and one Admin (user 2), so a P1
rule's deletion writes two notices. The refusal matrix rows for this route
are in service_helpers.MATRIX.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from service_helpers import HAMBURG_RULE, HAMBURG_RULES, ONE_RULE, RULE, RULES, call, make_app

from relay.escalation import EscalationStore, delete_rule, rule_from_document, save_rule, validate
from relay.service import demo_directory

CONTRACTS = Path(__file__).resolve().parents[1] / "specs" / "001-escalation-rules" / "contracts"
API = json.loads((CONTRACTS / "escalation-api.openapi.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((CONTRACTS / "escalation-rules.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def the_engine_can_delete():
    """The service turns any exception into a 500. Deleting through the engine first makes these tests fail for
    the right reason, the engine's own error, while the engine cannot yet delete (Chapter 8, Section 8.2)."""
    directory, at = demo_directory(), datetime(2026, 11, 24, 2, 30, tzinfo=timezone.utc)
    store = EscalationStore()
    save_rule(store, rule_from_document(RULE), directory.users[2], directory.projects[10], directory.users, at)
    delete_rule(store, "R-ROT-P1", directory.users[2], directory.projects[10], directory.users, at)


def test_ESC_AC25_an_admin_deletes_a_p1_rule_through_the_route_and_the_owner_and_admin_are_notified():
    app, store = make_app()
    call(app, "PUT", ONE_RULE, "demo-admin", RULE)
    status, _, body = call(app, "DELETE", ONE_RULE, "demo-admin")
    assert (status, body) == (200, {"rule_id": "R-ROT-P1", "deleted_at": "2026-11-24T02:30:00Z", "notices": 2})
    sent = [json.loads(i.body) for i in store.outbox() if i.kind == "rule_notice"]
    assert [m["to_user"] for m in sent] == [1, 2]
    assert sent[0]["subject"] == "[Relay] P1 escalation rule deleted in Rotterdam: Rotterdam night P1"
    assert "https://relay.example/ws-demo/projects/10/escalation-rules" in sent[0]["body"]


def test_the_success_body_matches_its_openapi_schema():
    app, _ = make_app()
    call(app, "PUT", ONE_RULE, "demo-admin", RULE)
    body = call(app, "DELETE", ONE_RULE, "demo-admin")[2]
    op = API["paths"]["/v1/projects/{pid}/escalation-rules/{rid}"]["delete"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "escalation-rules.schema.json#/$defs/RuleDeleted"}
    assert validate(body, {"$ref": "#/$defs/RuleDeleted"}, SCHEMA) == []


def test_the_contract_definition_matches_the_dataclass_field_for_field():
    import dataclasses

    from relay.escalation import model
    assert [f.name for f in dataclasses.fields(model.RuleDeleted)] == list(SCHEMA["$defs"]["RuleDeleted"]["properties"])


def test_a_deleted_rule_is_gone_from_the_routes_and_its_id_is_refused():
    app, _ = make_app()
    call(app, "PUT", ONE_RULE, "demo-admin", RULE)
    call(app, "DELETE", ONE_RULE, "demo-owner")
    assert call(app, "GET", ONE_RULE, "demo-member")[0] == 404
    assert call(app, "GET", RULES, "demo-member")[2] == {"rules": []}
    assert call(app, "DELETE", ONE_RULE, "demo-owner")[0] == 404
    assert call(app, "PUT", ONE_RULE, "demo-admin", RULE)[0] == 409


def test_a_member_is_refused_with_403_and_the_refusal_is_audited():
    app, store = make_app()
    call(app, "PUT", ONE_RULE, "demo-admin", RULE)
    assert call(app, "DELETE", ONE_RULE, "demo-member")[0] == 403
    assert call(app, "GET", ONE_RULE, "demo-member")[0] == 200
    entry = store.audit("R-ROT-P1")[-1]
    assert (entry.outcome, entry.code, entry.actor_id) == ("refused", "not_rule_editor", 3)


def test_another_projects_rule_cannot_be_deleted_through_this_project():
    app, _ = make_app()
    call(app, "PUT", HAMBURG_RULES + "/R-HAM-P1", "demo-admin", HAMBURG_RULE)
    assert call(app, "DELETE", "/v1/projects/10/escalation-rules/R-HAM-P1", "demo-admin")[0] == 404
    assert call(app, "GET", HAMBURG_RULES + "/R-HAM-P1", "demo-admin")[0] == 200


def test_a_guest_cannot_learn_that_an_uninvited_project_exists_and_nothing_is_audited():
    app, store = make_app()
    call(app, "PUT", HAMBURG_RULES + "/R-HAM-P1", "demo-admin", HAMBURG_RULE)
    before = len(store.audit())
    for method, body in (("DELETE", None), ("PUT", HAMBURG_RULE)):
        hidden = call(app, method, HAMBURG_RULES + "/R-HAM-P1", "demo-guest", body)
        missing = call(app, method, "/v1/projects/99/escalation-rules/R-HAM-P1", "demo-guest", body)
        assert (hidden[0], hidden[2]) == (missing[0], missing[2]) == (404, {"error": "not found"}), method
    assert len(store.audit()) == before

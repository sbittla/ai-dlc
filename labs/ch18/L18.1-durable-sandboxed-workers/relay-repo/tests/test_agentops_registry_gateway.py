"""The shared registry state, the service's agent gateway and the monitor's automated trip (4.30.0, ADR-051).

These close Chapter 14's deferred hooks: a kill switch tripped in one process is refused in every other on the
next use, the service verifies agent tokens on every request and audits each one, and DR-001/DR-003 can trip
an agent from the monitor."""

import io
import json
from types import SimpleNamespace

import pytest

from relay.agentops.gateway import AgentGateway, gateway_from_env, parse_project_teams
from relay.agentops.registry_state import SharedRegistry
from relay.audit import AuditTrail, TokenRejected, TokenService, killswitch
from relay.service.app import RelayApp
from relay.service.directory import demo_directory
from relay.service.monitor import trip_function
from relay.service.wsgi import ConfigError, with_agent_gateway
from relay.models import Task
from relay.store import TaskStore
from relay.worker import TriageQueue

KEY = b"k" * 32
T = 1_800_000_000.0
ISSUER = "https://token.actions.githubusercontent.com"
DATA = {
    "version": "test", "people": ["priya.n", "sam.o", "aisha.r"], "person_issuer": "https://login.relay.example",
    "agents": [{"agent_id": "triage-reader", "kind": "ci-job", "owner": "sam.o", "issuer": ISSUER,
                "subject": "repo:relay-example/relay:environment:triage-reader", "scopes": ["tasks:read:platform"],
                "max_ttl_seconds": 900}],
}
PROOF = {"iss": ISSUER, "sub": "repo:relay-example/relay:environment:triage-reader", "aud": "relay-token-exchange"}


def clock():
    return T


def services(db):
    registry = SharedRegistry(DATA, db, clock=clock)
    return registry, TokenService(registry, KEY, clock=clock, new_id=lambda: "jti-9")


def test_a_trip_in_one_process_is_refused_by_every_other_on_next_use(tmp_path):
    db = str(tmp_path / "relay.db")
    _, worker_tokens = services(db)
    monitor_registry, _ = services(db)
    token, _ = worker_tokens.exchange({**PROOF, "iat": T}, ["tasks:read:platform"])
    assert worker_tokens.verify(token, "tasks:read:platform")["sub"] == "triage-reader"
    killswitch.trip(monitor_registry, AuditTrail(), "triage-reader", "detection:DR-001", "export burst")
    with pytest.raises(TokenRejected) as exc:
        worker_tokens.verify(token, "tasks:read:platform")
    assert exc.value.code == "disabled"


def test_restoring_keeps_the_epoch_so_old_tokens_stay_dead(tmp_path):
    db = str(tmp_path / "relay.db")
    registry, tokens = services(db)
    old, _ = tokens.exchange({**PROOF, "iat": T}, ["tasks:read:platform"])
    trail = AuditTrail()
    killswitch.trip(registry, trail, "triage-reader", "aisha.r", "drill")
    killswitch.restore(registry, trail, "triage-reader", "aisha.r", "sam.o")
    _, other = services(db)
    with pytest.raises(TokenRejected) as exc:
        other.verify(old)
    assert exc.value.code == "revoked" and registry.get("triage-reader").epoch == 2
    fresh, _ = other.exchange({**PROOF, "iat": T}, ["tasks:read:platform"])
    assert other.verify(fresh)["ep"] == 2


def test_two_simultaneous_trips_both_move_the_epoch(tmp_path):
    db = str(tmp_path / "relay.db")
    a, _ = services(db)
    b, _ = services(db)
    a.disable("triage-reader")
    b.disable("triage-reader")
    assert a.get("triage-reader").epoch == 3


def app_with_gateway(tmp_path):
    db = str(tmp_path / "relay.db")
    registry, tokens = services(db)
    tasks = TaskStore(db)
    tasks.add(Task(1, 10, "Rotate the webhook keys"))
    app = RelayApp(demo_directory(), tasks, TriageQueue(db), clock=clock)
    trail = AuditTrail()
    return AgentGateway(app, tokens, trail, {10: "platform", 11: "payments"}), registry, tokens, trail


def call(gw, path, token, method="GET"):
    out = {}
    body = gw({"REQUEST_METHOD": method, "PATH_INFO": path, "HTTP_AUTHORIZATION": f"Bearer {token}",
               "wsgi.input": io.BytesIO(b"")}, lambda status, headers: out.update(status=status))
    return int(out["status"].split()[0]), json.loads(b"".join(body))


def test_the_gateway_verifies_every_agent_request_and_audits_each(tmp_path):
    gw, registry, tokens, trail = app_with_gateway(tmp_path)
    token, _ = tokens.exchange({**PROOF, "iat": T}, ["tasks:read:platform"])
    status, body = call(gw, "/v1/projects/10/tasks/1", token)
    assert status == 200 and body["title"] == "Rotate the webhook keys"
    status, body = call(gw, "/v1/projects/11/tasks/1", token)
    assert (status, body) == (403, {"error": "scope_missing"})
    killswitch.trip(registry, trail, "triage-reader", "detection:DR-001", "export burst")
    status, body = call(gw, "/v1/projects/10/tasks/1", token)
    assert (status, body) == (403, {"error": "disabled"})
    gateway = [r for r in trail.records if r["source"] == "relay.service"]
    assert [(r["outcome"], r["detail"].get("code")) for r in gateway] == [
        ("ok", None), ("refused", "scope_missing"), ("refused", "disabled")]
    assert gateway[0]["agent_id"] == "triage-reader" and gateway[0]["credential"] == "jti-9"
    assert all(token not in json.dumps(r) for r in trail.records)


def test_agents_may_use_only_the_routes_listed_for_them(tmp_path):
    gw, _, tokens, trail = app_with_gateway(tmp_path)
    token, _ = tokens.exchange({**PROOF, "iat": T}, ["tasks:read:platform"])
    assert call(gw, "/v1/triage-jobs", token, "POST") == (403, {"error": "route_not_for_agents"})
    assert call(gw, "/v1/projects/12/tasks/1", token) == (403, {"error": "no_team_for_project"})
    assert call(gw, "/v1/projects/10/tasks/1", "rla_forged.sig") == (401, {"error": "bad_signature"})
    assert [r["outcome"] for r in trail.records] == ["refused", "refused", "refused"]


def test_other_tokens_go_to_the_application_unchanged(tmp_path):
    gw, _, _, trail = app_with_gateway(tmp_path)
    status, _ = call(gw, "/v1/projects/10/tasks/1", "demo-member")
    assert status in (200, 404) and trail.records == []


def test_the_gateway_is_off_without_its_key_and_refuses_to_start_half_configured(tmp_path):
    app = SimpleNamespace(clock=clock)
    assert gateway_from_env(app, {}) is app
    with pytest.raises(ConfigError):
        with_agent_gateway(app, {"RELAY_AGENT_TOKEN_KEY": "ab" * 32})
    with pytest.raises(ValueError):
        parse_project_teams("10=Platform")
    assert parse_project_teams("10=platform, 11=payments") == {10: "platform", 11: "payments"}
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps(DATA), encoding="utf-8")
    env = {"RELAY_AGENT_TOKEN_KEY": "ab" * 32, "RELAY_AGENT_REGISTRY": str(registry),
           "RELAY_AUDIT_TRAIL": str(tmp_path / "trail.jsonl"), "RELAY_PROJECT_TEAMS": "10=platform",
           "RELAY_DB_PATH": str(tmp_path / "relay.db")}
    assert isinstance(gateway_from_env(app, env), AgentGateway)


def test_the_monitor_trips_through_the_shared_registry_only_when_it_can(tmp_path):
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps(DATA), encoding="utf-8")
    trail_path = tmp_path / "trail.jsonl"
    db = str(tmp_path / "relay.db")
    args = SimpleNamespace(dry_run=False, registry=str(registry), db=db, trail=str(trail_path))
    assert trip_function(SimpleNamespace(**{**vars(args), "dry_run": True})) is None
    assert trip_function(SimpleNamespace(**{**vars(args), "registry": None})) is None
    trip = trip_function(args)
    trip("triage-reader", "detection:DR-001", "export burst")
    trip("priya.n", "detection:DR-003", "not an agent")
    assert SharedRegistry(DATA, db).get("triage-reader").enabled is False
    records = [json.loads(line) for line in trail_path.read_text(encoding="utf-8").splitlines()]
    assert [(r["action"], r["outcome"]) for r in records] == [("killswitch.trip", "ok"), ("killswitch.trip", "refused")]

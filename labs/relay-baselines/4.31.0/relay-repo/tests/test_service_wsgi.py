"""The production WSGI entry point (4.21.0, ADR-015; wired in 4.25.0, ADR-031): configured from the environment,
no demo mode, one shared database for the task store, the queue, the rate limit and the escalation routes."""

import io
import json

import pytest

from relay.escalation import EscalationStore
from relay.service.directory import token_hash
from relay.service.sharedlimit import SharedRateLimiter
from relay.service.wsgi import ADAPTER_MISSING, ConfigError, create_app

LINK_BASE = "https://relay.example/ws-1"
RULE = {"rule_id": "R-ROT-P1", "project_id": 10, "priority": "P1", "name": "Rotterdam night P1",
        "steps": [{"number": 1, "delay_minutes": 10, "targets": [2]}]}


def directory_file(tmp_path):
    path = tmp_path / "directory.json"
    path.write_text(json.dumps({
        "workspace": "ws-1",
        "projects": [{"id": 10, "name": "Rotterdam"}],
        "users": [{"id": 1, "email": "o@example.com", "name": "O", "role": "Owner", "tz": "UTC",
                   "token_sha256": token_hash("t-owner")},
                  {"id": 2, "email": "a@example.com", "name": "A", "role": "Admin", "tz": "UTC",
                   "token_sha256": token_hash("t-admin")}],
    }), encoding="utf-8")
    return str(path)


def settings(tmp_path, **extra):
    env = {"RELAY_DB_PATH": str(tmp_path / "relay.db"), "RELAY_DIRECTORY_FILE": directory_file(tmp_path),
           "RELAY_LINK_BASE": LINK_BASE}
    env.update(extra)
    return env


def call(app, path, token=None, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else b""
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO(data),
               "CONTENT_LENGTH": str(len(data)) if body is not None else ""}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    seen = {}
    payload = b"".join(app(environ, lambda status, headers: seen.update(status=status)))
    return seen["status"], json.loads(payload)


def test_builds_the_app_from_the_environment(tmp_path):
    app = create_app(settings(tmp_path))
    status, body = call(app, "/healthz")
    assert status == "200 OK" and body["version"] == "4.31.0"
    assert isinstance(app.limiter, SharedRateLimiter)


def test_unknown_token_is_refused(tmp_path):
    app = create_app(settings(tmp_path))
    assert call(app, "/v1/triage-jobs/1", token="demo-owner")[0].startswith("401")


@pytest.mark.parametrize("drop", ["RELAY_DB_PATH", "RELAY_DIRECTORY_FILE", "RELAY_LINK_BASE"])
def test_missing_settings_stop_the_process(tmp_path, drop):
    env = settings(tmp_path)
    del env[drop]
    with pytest.raises(ConfigError, match=drop):
        create_app(env)


def test_an_empty_environment_stops_the_process():
    with pytest.raises(ConfigError):
        create_app({})


def test_a_plain_http_link_base_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="https"):
        create_app(settings(tmp_path, RELAY_LINK_BASE="http://relay.example/ws-1"))


def test_a_cloud_database_host_is_refused_until_the_adapter_exists(tmp_path):
    with pytest.raises(ConfigError) as err:
        create_app(settings(tmp_path, RELAY_DB_HOST="relay.cluster.internal"))
    assert str(err.value) == ADAPTER_MISSING


def test_escalation_rules_live_in_the_shared_database_not_in_process_memory(tmp_path):
    """4.21.0 built the routes on a private in-memory store, so a second process never saw a saved rule."""
    first, second = create_app(settings(tmp_path)), create_app(settings(tmp_path))
    assert call(first, "/v1/projects/10/escalation-rules/R-ROT-P1", "t-admin", "PUT", RULE)[0].startswith("201")
    assert call(second, "/v1/projects/10/escalation-rules", "t-owner")[1] == {"rules": [RULE]}
    assert [r["rule_id"] for r in EscalationStore(str(tmp_path / "relay.db")).rule_documents(10)] == ["R-ROT-P1"]


def test_rule_notices_link_to_the_configured_workspace(tmp_path):
    app = create_app(settings(tmp_path))
    call(app, "/v1/projects/10/escalation-rules/R-ROT-P1", "t-admin", "PUT", RULE)
    changed = dict(RULE, name="Rotterdam night P1, revised")
    assert call(app, "/v1/projects/10/escalation-rules/R-ROT-P1", "t-admin", "PUT", changed)[0].startswith("200")
    bodies = [item.body for item in EscalationStore(str(tmp_path / "relay.db")).outbox()]
    assert bodies and all(LINK_BASE + "/" in b for b in bodies)

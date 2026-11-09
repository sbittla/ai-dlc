"""The production WSGI entry point (4.21.0, ADR-015): configured from the environment, no demo mode."""

import io
import json

import pytest

from relay.service.directory import token_hash
from relay.service.sharedlimit import SharedRateLimiter
from relay.service.wsgi import ConfigError, create_app


def directory_file(tmp_path):
    path = tmp_path / "directory.json"
    path.write_text(json.dumps({
        "workspace": "ws-1",
        "projects": [{"id": 10, "name": "Rotterdam"}],
        "users": [{"id": 1, "email": "o@example.com", "name": "O", "role": "Owner", "tz": "UTC",
                   "token_sha256": token_hash("t-owner")}],
    }), encoding="utf-8")
    return str(path)


def call(app, path, token=None):
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": path, "wsgi.input": io.BytesIO(b"")}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    seen = {}
    body = b"".join(app(environ, lambda status, headers: seen.update(status=status)))
    return seen["status"], json.loads(body)


def test_builds_the_app_from_the_environment(tmp_path):
    app = create_app({"RELAY_DB_PATH": str(tmp_path / "relay.db"), "RELAY_DIRECTORY_FILE": directory_file(tmp_path)})
    status, body = call(app, "/healthz")
    assert status == "200 OK" and body["version"] == "4.24.0"
    assert isinstance(app.limiter, SharedRateLimiter)


def test_unknown_token_is_refused(tmp_path):
    app = create_app({"RELAY_DB_PATH": str(tmp_path / "relay.db"), "RELAY_DIRECTORY_FILE": directory_file(tmp_path)})
    assert call(app, "/v1/triage-jobs/1", token="demo-owner")[0].startswith("401")


@pytest.mark.parametrize("env", [{}, {"RELAY_DB_PATH": "relay.db"}, {"RELAY_DIRECTORY_FILE": "d.json"}])
def test_missing_settings_stop_the_process(env):
    with pytest.raises(ConfigError):
        create_app(env)

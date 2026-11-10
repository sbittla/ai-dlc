"""The service over a real socket on 127.0.0.1, as later chapters deploy it."""

import json
import queue
import threading
import urllib.error
import urllib.request
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest

from relay.service.__main__ import build_app
from relay.service.directory import demo_directory


class Silent(WSGIRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def base_url(tmp_path):
    # SQLite connections belong to the thread that opened them, so the app is built
    # in the server's own thread, exactly as `python -m relay.service` does.
    ready = queue.Queue()
    holder = {}

    def serve():
        app = build_app(str(tmp_path / "relay.db"), demo_directory(), demo=True)
        holder["httpd"] = httpd = make_server("127.0.0.1", 0, app, handler_class=Silent)
        ready.put(httpd.server_port)
        httpd.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    port = ready.get(timeout=10)
    yield f"http://127.0.0.1:{port}"
    holder["httpd"].shutdown()
    thread.join(timeout=10)
    holder["httpd"].server_close()


def request(url, method="GET", token=None, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health_and_a_task_over_http(base_url):
    assert request(base_url + "/healthz")[1]["version"] == "4.29.0"
    status, body = request(base_url + "/v1/projects/10/tasks/100", token="demo-member")
    assert status == 200 and body["title"] == "Scanner gateway offline"


def test_submit_and_replay_over_http(base_url):
    h = {"Idempotency-Key": "http-ticket-01"}
    s1, j1 = request(base_url + "/v1/triage-jobs", "POST", "demo-member", {"text": "Locked out after SSO"}, h)
    s2, j2 = request(base_url + "/v1/triage-jobs", "POST", "demo-member", {"text": "Locked out after SSO"}, h)
    assert (s1, s2) == (202, 202) and j1["id"] == j2["id"]

"""Relay's HTTP service, called as a WSGI application (no sockets)."""

import io
import json
from datetime import date

import pytest

from relay import __version__
from relay.models import Task
from relay.service import RelayApp, demo_directory
from relay.service.ratelimit import RateLimiter
from relay.store import TaskStore
from relay.worker import TriageQueue

T0 = 1_794_000_000.0


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    tasks = TaskStore(":memory:")
    tasks.add(Task(100, 10, "Scanner gateway offline", "open", date(2026, 11, 20), 3))
    tasks.add(Task(102, 11, "Quarterly stock count", "done", None, 2))
    queue = TriageQueue(":memory:")
    clock = Clock(T0)
    app = RelayApp(demo_directory(), tasks, queue, clock=clock)
    return app, queue, clock


def call(app, method, path, token=None, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO(data),
               "CONTENT_LENGTH": str(len(data)) if (body is not None or raw is not None) else ""}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    for k, v in (headers or {}).items():
        environ["HTTP_" + k.upper().replace("-", "_")] = v
    seen = {}

    def start_response(status, hdrs):
        seen["status"], seen["headers"] = int(status.split()[0]), dict(hdrs)

    payload = b"".join(app(environ, start_response))
    return seen["status"], seen["headers"], json.loads(payload)


def submit(app, key="ticket-0001", text="The board shows a 500 error", token="demo-member"):
    return call(app, "POST", "/v1/triage-jobs", token, {"text": text}, {"Idempotency-Key": key})


def test_health_needs_no_token_and_reports_version_and_stall(env):
    app, _, _ = env
    status, _, body = call(app, "GET", "/healthz")
    assert status == 200 and body["version"] == __version__ == "4.28.0"
    assert body["worker"] == {"last_pass_age_s": None, "stalled": True}   # no worker has run yet


def test_v1_routes_need_a_known_token(env):
    app, _, _ = env
    assert call(app, "GET", "/v1/projects/10/tasks/100")[0] == 401
    status, headers, _ = call(app, "GET", "/v1/projects/10/tasks/100", token="not-a-token")
    assert status == 401 and headers["WWW-Authenticate"] == "Bearer"


def test_task_view_goes_through_roles(env):
    app, _, _ = env
    status, _, body = call(app, "GET", "/v1/projects/10/tasks/100", token="demo-guest")
    assert status == 200 and body["due_date"] == "2026-11-20"           # RLY-412 stays fixed
    assert call(app, "GET", "/v1/projects/11/tasks/102", token="demo-guest")[0] == 403   # not invited
    assert call(app, "GET", "/v1/projects/10/tasks/102", token="demo-owner")[0] == 404   # wrong project
    assert call(app, "GET", "/v1/projects/99/tasks/100", token="demo-owner")[0] == 404


def test_submit_returns_202_and_location_without_calling_triage(env):
    app, queue, _ = env
    status, headers, body = submit(app)
    assert status == 202 and headers["Location"] == f"/v1/triage-jobs/{body['id']}"
    assert body["status"] == "queued" and body["suggestion"] is None
    assert queue.counts()["queued"] == 1


def test_replay_with_same_key_returns_the_same_job(env):
    app, queue, _ = env
    _, _, first = submit(app)
    status, headers, again = submit(app)
    assert status == 202 and again["id"] == first["id"] and headers["Idempotent-Replayed"] == "true"
    assert queue.counts()["queued"] == 1


def test_same_key_different_body_is_422(env):
    app, _, _ = env
    submit(app)
    assert submit(app, text="Something else entirely")[0] == 422


@pytest.mark.parametrize("key", ["", "short", "has space in it", "x" * 65])
def test_idempotency_key_is_required_and_well_formed(env, key):
    app, _, _ = env
    headers = {"Idempotency-Key": key} if key else {}
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", {"text": "t"}, headers)[0] == 400


def test_body_validation(env):
    app, _, _ = env
    k = {"Idempotency-Key": "ticket-0001"}
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", {"text": "t", "priority": "P1"}, k)[0] == 400
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", raw=b"{not json", headers=k)[0] == 400
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", raw=b"x" * 20_000, headers=k)[0] == 413
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", {"text": "x" * 8_001}, k)[0] == 413


def test_errors_do_not_echo_the_ticket(env):
    app, _, _ = env
    submit(app, text="Customer 4471 card data exposed")
    _, _, body = submit(app, text="Customer 4471 card data exposed, again")
    assert "4471" not in json.dumps(body)


def test_guests_cannot_submit_or_read_triage_jobs(env):
    app, _, _ = env
    assert submit(app, token="demo-guest")[0] == 403
    _, _, job = submit(app)
    assert call(app, "GET", f"/v1/triage-jobs/{job['id']}", token="demo-guest")[0] == 403


def test_job_view_never_contains_the_ticket_text(env):
    app, _, _ = env
    _, _, job = submit(app, text="Customer 4471 card data exposed")
    status, _, body = call(app, "GET", f"/v1/triage-jobs/{job['id']}", token="demo-admin")
    assert status == 200 and "4471" not in json.dumps(body)


def test_rate_limit_is_per_token_and_says_when_to_retry(env):
    app, _, clock = env
    app.limiter = RateLimiter(limit=3)
    for _ in range(3):
        assert call(app, "GET", "/v1/projects/10/tasks/100", token="demo-owner")[0] == 200
    clock.t = T0 + 20
    status, headers, _ = call(app, "GET", "/v1/projects/10/tasks/100", token="demo-owner")
    assert status == 429 and int(headers["Retry-After"]) >= 1
    assert call(app, "GET", "/v1/projects/10/tasks/100", token="demo-admin")[0] == 200


def test_default_rate_limit_is_600_per_minute():
    limiter = RateLimiter()
    assert all(limiter.check("t", 60.0 + i / 100)[0] for i in range(600))
    assert limiter.check("t", 66.0) == (False, 54)
    assert limiter.check("t", 120.0)[0] is True


def test_wrong_methods_and_unknown_paths(env):
    app, _, _ = env
    assert call(app, "DELETE", "/v1/projects/10/tasks/100", token="demo-owner")[0] == 405
    assert call(app, "GET", "/v1/nothing", token="demo-owner")[0] == 404
    assert call(app, "GET", "/admin")[0] == 404


def test_end_to_end_with_the_worker(env):
    from relay.worker.runner import Worker
    from relay.worker.triage import SimulatedTriage
    app, queue, clock = env
    _, _, job = submit(app, text="Since this morning the board is down for everyone")
    Worker(queue, SimulatedTriage(invalid_rate=0, unavailable_rate=0), clock=clock).run_once()
    status, _, body = call(app, "GET", f"/v1/triage-jobs/{job['id']}", token="demo-member")
    assert status == 200 and body["status"] == "done"
    assert body["suggestion"]["priority"] == "P1" and body["applies_to_task"] is False
    _, _, health = call(app, "GET", "/healthz")
    assert health["worker"]["stalled"] is False and health["queue"]["done"] == 1


def test_job_routes_need_a_known_token(env):
    app, _, _ = env
    _, _, job = submit(app)
    assert call(app, "GET", f"/v1/triage-jobs/{job['id']}")[0] == 401
    assert call(app, "POST", "/v1/triage-jobs", None, {"text": "t"}, {"Idempotency-Key": "ticket-0002"})[0] == 401


def test_another_workspaces_job_is_404_not_403(env):
    app, queue, _ = env
    other, _ = queue.enqueue("ws-other", "ticket-0001", "Their ticket", T0)
    status, _, body = call(app, "GET", f"/v1/triage-jobs/{other.id}", token="demo-admin")
    assert status == 404 and "Their" not in json.dumps(body)


def test_deeply_nested_json_is_400_not_500(env):
    app, _, _ = env
    k = {"Idempotency-Key": "ticket-0001"}
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", raw=b"[" * 5000 + b"]" * 5000, headers=k)[0] == 400
    assert call(app, "POST", "/v1/triage-jobs", "demo-member", {"text": [[[["x"]]]]}, k)[0] == 400


def test_an_unexpected_error_is_logged_and_returns_500_without_details(env, caplog):
    app, _, _ = env

    def boom(*args):
        raise RuntimeError("secret detail")
    app.tasks.get = boom
    status, _, body = call(app, "GET", "/v1/projects/10/tasks/100", token="demo-owner")
    assert status == 500 and body == {"error": "internal error"}
    assert "unhandled error on GET /v1/projects/10/tasks/100" in caplog.text


def test_rate_limit_is_keyed_by_token():
    from relay.service.directory import token_hash
    app_limiter = RateLimiter(limit=1)
    assert app_limiter.check(token_hash("demo-owner"), 0)[0] is True
    assert app_limiter.check(token_hash("demo-owner"), 1)[0] is False
    assert app_limiter.check(token_hash("demo-admin"), 1)[0] is True


def test_demo_tokens_refuse_a_public_bind():
    from relay.service.__main__ import main
    with pytest.raises(SystemExit) as exc:
        main(["--db", ":memory:", "--demo", "--host", "0.0.0.0"])
    assert exc.value.code == 2

"""Relay's HTTP service: a WSGI application on the standard library (ADR-007, ADR-008).

Routes (all JSON):

    GET  /healthz                         liveness, version, queue depth, worker stall flag
    GET  /v1/projects/{pid}/tasks/{tid}   a task as the caller sees it (relay.api.task_view)
    POST /v1/triage-jobs                  queue a support ticket for triage; needs Idempotency-Key
    GET  /v1/triage-jobs/{id}             a triage job's status and suggestion

Every /v1 route needs `Authorization: Bearer <token>`. The service is the
trust boundary between callers and Relay's modules: it authenticates, rate
limits (600 requests per minute per token), caps body size, and validates
input before any module sees it. It never calls the triage model itself;
it queues a job and returns 202, and the worker does the slow part.

Errors never echo request bodies, so ticket text cannot leak into logs or
error pages through this layer.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Callable, Iterable

from .. import __version__
from ..api import task_view
from ..store import TaskStore
from ..worker import IdempotencyConflict, TriageQueue, is_stalled
from .directory import Directory
from .ratelimit import RateLimiter
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..worker.queue import Job

MAX_BODY_BYTES = 16_384
MAX_TICKET_CHARS = 8_000
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
TASK_PATH = re.compile(r"^/v1/projects/(\d+)/tasks/(\d+)$")
JOB_PATH = re.compile(r"^/v1/triage-jobs/(\d+)$")

_REASONS = {200: "OK", 202: "Accepted", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
            404: "Not Found", 405: "Method Not Allowed", 411: "Length Required", 413: "Content Too Large",
            422: "Unprocessable Content", 429: "Too Many Requests", 500: "Internal Server Error"}


class Response:
    def __init__(self, status: int, body: dict, headers: dict[str, str] | None = None) -> None:
        self.status, self.body, self.headers = status, body, dict(headers or {})


def error(status: int, message: str, **headers: str) -> Response:
    return Response(status, {"error": message}, headers)


class RelayApp:
    """The WSGI callable. Construct once per process; pass it to any WSGI server."""

    def __init__(self, directory: Directory, tasks: TaskStore, queue: TriageQueue,
                 clock: Callable[[], float] = time.time, limiter: RateLimiter | None = None) -> None:
        self.directory, self.tasks, self.queue, self.clock = directory, tasks, queue, clock
        self.limiter = limiter or RateLimiter()

    # ------------------------------------------------------------ WSGI

    def __call__(self, environ: dict, start_response) -> Iterable[bytes]:
        try:
            resp = self.handle(environ)
        except Exception:  # noqa: BLE001 - the boundary must not leak tracebacks
            resp = error(500, "internal error")
        payload = json.dumps(resp.body, sort_keys=True).encode("utf-8")
        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))]
        headers += sorted(resp.headers.items())
        start_response(f"{resp.status} {_REASONS.get(resp.status, '')}".rstrip(), headers)
        return [payload]

    def handle(self, environ: dict) -> Response:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        now = self.clock()
        if path == "/healthz":
            return self.health(now) if method == "GET" else error(405, "method not allowed")
        if not path.startswith("/v1/"):
            return error(404, "not found")

        user = self.directory.authenticate(_bearer(environ))
        if user is None:
            return error(401, "missing or unknown token", **{"WWW-Authenticate": "Bearer"})
        allowed, retry_after = self.limiter.check(str(user.id), now)
        if not allowed:
            return error(429, "rate limit: 600 requests per minute per token", **{"Retry-After": str(retry_after)})

        if (m := TASK_PATH.match(path)):
            return self.get_task(user, int(m[1]), int(m[2])) if method == "GET" else error(405, "method not allowed")
        if path == "/v1/triage-jobs":
            return self.create_job(user, environ, now) if method == "POST" else error(405, "method not allowed")
        if (m := JOB_PATH.match(path)):
            return self.get_job(user, int(m[1])) if method == "GET" else error(405, "method not allowed")
        return error(404, "not found")

    # ------------------------------------------------------------ routes

    def health(self, now: float) -> Response:
        last = self.queue.last_pass_at()
        return Response(200, {
            "status": "ok",
            "version": __version__,
            "queue": self.queue.counts(),
            "worker": {"last_pass_age_s": None if last is None else round(now - last, 1),
                       "stalled": is_stalled(last, now)},
        })

    def get_task(self, user, project_id: int, task_id: int) -> Response:
        project = self.directory.projects.get(project_id)
        if project is None:
            return error(404, "not found")
        try:
            task = self.tasks.get(task_id)
            return Response(200, task_view(task, project, user))
        except (KeyError, ValueError):
            return error(404, "not found")
        except PermissionError:
            return error(403, "forbidden")

    def create_job(self, user, environ: dict, now: float) -> Response:
        if user.role == "Guest":
            return error(403, "forbidden")
        key = environ.get("HTTP_IDEMPOTENCY_KEY", "")
        if not IDEMPOTENCY_KEY.match(key):
            return error(400, "Idempotency-Key header required: 8-64 characters from A-Z, a-z, 0-9, - and _")
        body, problem = _read_json(environ)
        if problem is not None:
            return problem
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip() or set(body) != {"text"}:
            return error(400, 'body must be {"text": "<ticket text>"}')
        if len(text) > MAX_TICKET_CHARS:
            return error(413, f"ticket text over {MAX_TICKET_CHARS} characters")
        try:
            job, created = self.queue.enqueue(self.directory.workspace, key, text, now)
        except IdempotencyConflict:
            return error(422, "Idempotency-Key already used with a different body")
        headers = {"Location": f"/v1/triage-jobs/{job.id}"}
        if not created:
            headers["Idempotent-Replayed"] = "true"
        return Response(202, job_view(job), headers)

    def get_job(self, user, job_id: int) -> Response:
        if user.role == "Guest":
            return error(403, "forbidden")
        try:
            job = self.queue.get(job_id)
        except KeyError:
            return error(404, "not found")
        if job.workspace != self.directory.workspace:
            return error(404, "not found")  # do not reveal other workspaces' jobs
        return Response(200, job_view(job))


def job_view(job) -> dict:
    """A triage job as callers see it. The ticket text is never echoed back."""
    view = {
        "id": job.id,
        "status": job.status,
        "attempts": job.attempts,
        "created_at": _iso(job.created_at),
        "suggestion": None,
    }
    if job.result is not None:
        view["suggestion"] = job.result["suggestion"]
        view["model"] = job.result["model"]
        view["prompt"] = job.result["prompt"]
        view["applies_to_task"] = False  # a person confirms or overrides (D3, ESC-N01)
    if job.status == "needs_human":
        view["reason"] = job.last_error
    return view


def _bearer(environ: dict) -> str | None:
    header = environ.get("HTTP_AUTHORIZATION", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _read_json(environ: dict) -> tuple[object, Response | None]:
    raw_len = environ.get("CONTENT_LENGTH") or ""
    if not raw_len.isdigit():
        return None, error(411, "Content-Length required")
    length = int(raw_len)
    if length > MAX_BODY_BYTES:
        return None, error(413, f"body over {MAX_BODY_BYTES} bytes")
    raw = environ["wsgi.input"].read(length)
    try:
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, error(400, "body is not valid JSON")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

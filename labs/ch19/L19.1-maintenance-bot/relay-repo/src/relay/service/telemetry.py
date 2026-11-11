"""HTTP telemetry for the service: a WSGI middleware around RelayApp (added in 4.27.0; ADR-036).

For every request it records one SERVER span and one measurement of `http.server.request.duration`, with the
method, the route template and the status code, and nothing else: no header, no query string, no body, no
user. Routes are templates (`/v1/projects/{pid}/tasks/{tid}`), never raw paths, so a metric has one series
per route rather than one per task, and a path that matches no route records no route at all.

Server spans follow the HTTP conventions: a 5xx response is an error, a 4xx response is not (the server did
its job). A 401, 403 or 429 also writes a security event, a log record with the network the request came
from (a /24 or /48 prefix, never the address) and, if a key is configured, a keyed fingerprint of the
presented credential so that detection can count distinct credentials without anyone being able to recover
one (`infra/detection/service-rules.json`).

An incoming `traceparent` is not trusted: the service starts its own trace and keeps a well-formed incoming
context as a span link, so a caller can correlate but cannot write into Relay's traces.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from typing import Callable, Iterable

from ..telemetry import semconv
from ..telemetry.trace import ERROR, SERVER, UNSET, parse_traceparent
from .app import JOB_PATH, TASK_PATH
from .escalation_routes import RULE_PATH, RULES_PATH, TASK_ACTION_PATH

SECURITY_STATUSES = {401: "auth.failure", 403: "forbidden", 429: "rate_limited"}
LATENCY_SLO_S = 0.25  # SLO-API-LATENCY's threshold, a bucket boundary of the duration histogram (docs/slo/slos.json)


def route_template(path: str) -> str | None:
    """The route a path matches, as a template; None for a path no route serves."""
    if path in ("/healthz", "/v1/triage-jobs"):
        return path
    if TASK_PATH.match(path):
        return "/v1/projects/{pid}/tasks/{tid}"
    if JOB_PATH.match(path):
        return "/v1/triage-jobs/{id}"
    if RULES_PATH.match(path):
        return "/v1/projects/{pid}/escalation-rules"
    if RULE_PATH.match(path):
        return "/v1/projects/{pid}/escalation-rules/{rid}"
    if (m := TASK_ACTION_PATH.match(path)):
        return "/v1/projects/{pid}/tasks/{tid}/" + m[3]
    return None


def client_network(environ: dict, trusted_proxies: tuple = ()) -> str:
    """The caller's network prefix. X-Forwarded-For is read only when the peer is a trusted proxy."""
    peer = environ.get("REMOTE_ADDR", "")
    addr = peer
    try:
        if trusted_proxies and any(ipaddress.ip_address(peer) in net for net in trusted_proxies):
            forwarded = environ.get("HTTP_X_FORWARDED_FOR", "").split(",")
            addr = forwarded[-1].strip() or peer  # the hop the trusted proxy added, not the client's claim
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return "unknown"
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def fingerprint(key: bytes | None, environ: dict) -> str | None:
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not key or not header:
        return None
    return hmac.new(key, header.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


class TelemetryMiddleware:
    def __init__(self, app, tracer, meter, logger, fingerprint_key: bytes | None = None,
                 trusted_proxies: tuple = (), clock_ns: Callable[[], int] = time.time_ns, flush=None) -> None:
        self.app, self.tracer, self.logger, self.clock_ns = app, tracer, logger, clock_ns
        self.meter, self.key, self.trusted, self.flush = meter, fingerprint_key, tuple(trusted_proxies), flush
        self.duration = meter.histogram(semconv.HTTP_SERVER_REQUEST_DURATION, "s", "HTTP server request duration",
                                        limit=300, boundaries=semconv.DURATION_BUCKETS)
        self.sli = meter.counter("relay.sli.events", "{event}", "SLI events by SLO and whether they were good", limit=8)

    def __getattr__(self, name):  # tests and tools reach the wrapped app's attributes (limiter, queue, ...)
        return getattr(self.app, name)

    def __call__(self, environ: dict, start_response) -> Iterable[bytes]:
        start = self.clock_ns()
        method = environ.get("REQUEST_METHOD", "GET")
        method = method if method in semconv.KNOWN_METHODS else semconv.OTHER_METHOD
        route = route_template(environ.get("PATH_INFO", "/"))
        attrs = {semconv.HTTP_REQUEST_METHOD: method}
        if route:
            attrs[semconv.HTTP_ROUTE] = route
        incoming = parse_traceparent(environ.get("HTTP_TRACEPARENT"))
        span = self.tracer.start(f"{method} {route}" if route else method, SERVER, attributes=attrs, start_ns=start,
                                 links=[incoming] if incoming else [])
        seen = {}

        def capture(status, headers, exc_info=None):
            seen["status"] = int(str(status).split(" ", 1)[0])
            return start_response(status, headers, exc_info) if exc_info else start_response(status, headers)

        try:
            body = list(self.app(environ, capture))
        except Exception:
            seen["status"] = 500
            raise
        finally:
            self._finish(environ, span, attrs, start, seen.get("status", 500))
        return body

    def _finish(self, environ: dict, span, attrs: dict, start: int, status: int) -> None:
        end = self.clock_ns()
        span.set(semconv.HTTP_RESPONSE_STATUS_CODE, status)
        if status >= 500:
            span.set(semconv.ERROR_TYPE, str(status))
        self.tracer.end(span, ERROR if status >= 500 else UNSET, end_ns=end)
        seconds = (end - start) / 1e9
        self.duration.record(seconds, {**attrs, semconv.HTTP_RESPONSE_STATUS_CODE: status})
        route = attrs.get(semconv.HTTP_ROUTE, "")
        if route.startswith("/v1/"):
            self.sli.add(1, {semconv.RELAY_SLO_ID: "SLO-API-AVAIL", semconv.RELAY_SLI_GOOD: status < 500})
            self.sli.add(1, {semconv.RELAY_SLO_ID: "SLO-API-LATENCY",
                             semconv.RELAY_SLI_GOOD: status < 500 and seconds <= LATENCY_SLO_S})
        event = SECURITY_STATUSES.get(status)
        if event:
            fields = {semconv.RELAY_SECURITY_EVENT: event, semconv.HTTP_RESPONSE_STATUS_CODE: status,
                      semconv.RELAY_CLIENT_NETWORK: client_network(environ, self.trusted), **attrs}
            fp = fingerprint(self.key, environ)
            if fp:
                fields[semconv.RELAY_CREDENTIAL_FINGERPRINT] = fp
            self.logger.emit("WARN", event, fields, span=span, at_ns=end)
        if self.flush is not None:
            self.flush()

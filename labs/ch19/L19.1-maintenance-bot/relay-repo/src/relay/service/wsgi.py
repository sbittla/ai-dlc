"""The WSGI entry point for a production server (added in 4.21.0; ADR-015; wired in 4.25.0, ADR-031).

    gunicorn --bind 0.0.0.0:8080 --workers 2 relay.service.wsgi:application

ADR-008 kept the HTTP service on the standard library and said a production
server would be a new dependency with its own ADR. ADR-015 records that
decision: the container image (`deploy/Containerfile`) installs the server,
and nothing under `src/` imports it. This module only builds the same
`RelayApp` from environment variables, once per server process.

    RELAY_DB_PATH          the database file shared with the worker (required)
    RELAY_DIRECTORY_FILE   users, projects and token hashes as JSON (required)
    RELAY_LINK_BASE        the workspace's web address, for links in messages (required from 4.25.0)
    RELAY_DB_HOST          set by the cloud task definition for the PostgreSQL adapter; refused (see below)
    RELAY_TELEMETRY_DIR    where to write OTLP JSON lines for the collector sidecar (4.27.0, ADR-036; optional)
    RELAY_TELEMETRY_KEY    hex key for credential fingerprints in security events (Restricted; optional)
    RELAY_TRUSTED_PROXIES  comma-separated networks whose X-Forwarded-For is believed (the load balancer's)
    RELAY_ENVIRONMENT      the deployment environment's name in telemetry (default "nonprod")
    RELAY_AGENT_TOKEN_KEY  hex key that signs agent tokens (Restricted; 4.30.0, ADR-051; optional). When set,
                           RELAY_AGENT_REGISTRY (agents.json), RELAY_AUDIT_TRAIL (JSON lines) and
                           RELAY_PROJECT_TEAMS (10=platform,...) are required, and agent tokens are verified
                           against the shared registry state on every request (relay.agentops.gateway)

4.25.0 wires in what 4.21.0 left loose (ADR-031): the escalation routes use
the shared database rather than a private in-memory store, links in rule
notices use the configured workspace address, and the rate limit is counted
in the shared database (`SharedRateLimiter`), never in one process's memory.

There is no demo mode here: the demo tokens are public, so they stay with
`python -m relay.service --demo` on a loopback address.

Relay still stores data in SQLite; the PostgreSQL store adapter needs its own
dependency ADR (ADR-014, ADR-028). A cloud task sets `RELAY_DB_HOST`. Rather
than fall back to a private SQLite file inside one task, which the worker in
another task would never see, the process refuses to start (fail closed).
"""

from __future__ import annotations

import ipaddress
import os
import time
from typing import Iterable, Mapping

from ..escalation import EscalationStore
from ..store import TaskStore
from ..worker import TriageQueue
from .app import RelayApp
from .directory import Directory
from .sharedlimit import SharedRateLimiter
from .telemetry import TelemetryMiddleware
from ..agentops.gateway import gateway_from_env

REQUIRED = ("RELAY_DB_PATH", "RELAY_DIRECTORY_FILE", "RELAY_LINK_BASE")
ADAPTER_MISSING = ("RELAY_DB_HOST is set, but this release has no PostgreSQL store adapter (ADR-014); "
                   "refusing to start on a private SQLite file")


class ConfigError(Exception):
    """A required setting is missing or unusable; the process must not start half-configured."""


def check_settings(env: Mapping[str, str]) -> None:
    """Raise ConfigError unless the settings describe a database every process shares."""
    if env.get("RELAY_DB_HOST"):
        raise ConfigError(ADAPTER_MISSING)
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise ConfigError("missing required settings: " + ", ".join(missing))
    if not env["RELAY_LINK_BASE"].startswith("https://"):
        raise ConfigError("RELAY_LINK_BASE must be an https:// address")


def create_app(env: Mapping[str, str] | None = None) -> RelayApp:
    env = os.environ if env is None else env
    check_settings(env)
    db = env["RELAY_DB_PATH"]
    directory = Directory.load(env["RELAY_DIRECTORY_FILE"])
    return RelayApp(directory, TaskStore(db), TriageQueue(db), limiter=SharedRateLimiter(db),
                    escalation=EscalationStore(db), link_base=env["RELAY_LINK_BASE"].rstrip("/"))


def instrument(app: RelayApp, env: Mapping[str, str], flush_every_s: float = 10.0):
    """Wrap `app` in the telemetry middleware if RELAY_TELEMETRY_DIR is set; otherwise return it unchanged."""
    from ..telemetry import FileExporter, Logger, Meter, Tracer
    directory = env.get("RELAY_TELEMETRY_DIR")
    if not directory:
        return app
    try:
        key = bytes.fromhex(env["RELAY_TELEMETRY_KEY"]) if env.get("RELAY_TELEMETRY_KEY") else None
        proxies = tuple(ipaddress.ip_network(c.strip()) for c in env.get("RELAY_TRUSTED_PROXIES", "").split(",")
                        if c.strip())
    except ValueError as exc:
        raise ConfigError(f"telemetry settings: {exc}") from None
    exporter = FileExporter(directory, "relay-service", env.get("RELAY_ENVIRONMENT", "nonprod"))
    meter, started, last = Meter(), time.time_ns(), [time.monotonic()]

    def flush() -> None:
        if time.monotonic() - last[0] >= flush_every_s:
            exporter.flush(meter, started, time.time_ns())
            last[0] = time.monotonic()
    return TelemetryMiddleware(app, Tracer(exporter), meter, Logger(exporter), key, proxies, flush=flush)


def with_agent_gateway(app: RelayApp, env: Mapping[str, str]):
    """4.30.0 (ADR-051): verify agent tokens and audit agent requests when RELAY_AGENT_TOKEN_KEY is set."""
    try:
        return gateway_from_env(app, env)
    except ValueError as exc:
        raise ConfigError(f"agent gateway settings: {exc}") from None


_app = None


def application(environ: dict, start_response) -> Iterable[bytes]:
    """Build the app on the first request in each process (after the server forks), then reuse it."""
    global _app
    if _app is None:
        _app = instrument(with_agent_gateway(create_app(), os.environ), os.environ)
    return _app(environ, start_response)

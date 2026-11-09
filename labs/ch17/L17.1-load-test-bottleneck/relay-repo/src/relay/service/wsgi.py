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

import os
from typing import Iterable, Mapping

from ..escalation import EscalationStore
from ..store import TaskStore
from ..worker import TriageQueue
from .app import RelayApp
from .directory import Directory
from .sharedlimit import SharedRateLimiter

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


_app: RelayApp | None = None


def application(environ: dict, start_response) -> Iterable[bytes]:
    """Build the app on the first request in each process (after the server forks), then reuse it."""
    global _app
    if _app is None:
        _app = create_app()
    return _app(environ, start_response)

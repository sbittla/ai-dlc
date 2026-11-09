"""The WSGI entry point for a production server (added in 4.21.0; ADR-015).

    gunicorn --bind 0.0.0.0:8080 --workers 2 relay.service.wsgi:application

ADR-008 kept the HTTP service on the standard library and said a production
server would be a new dependency with its own ADR. ADR-015 records that
decision: the container image (`deploy/Containerfile`) installs the server,
and nothing under `src/` imports it. This module only builds the same
`RelayApp` from environment variables, once per server process.

    RELAY_DB_PATH          the database file shared with the worker (required)
    RELAY_DIRECTORY_FILE   users, projects and token hashes as JSON (required)

There is no demo mode here: the demo tokens are public, so they stay with
`python -m relay.service --demo` on a loopback address. Because a production
server runs several processes, the rate limit is counted in the shared
database (`SharedRateLimiter`), never in one process's memory.
"""

from __future__ import annotations

import os
from typing import Iterable, Mapping

from ..store import TaskStore
from ..worker import TriageQueue
from .app import RelayApp
from .directory import Directory
from .sharedlimit import SharedRateLimiter

REQUIRED = ("RELAY_DB_PATH", "RELAY_DIRECTORY_FILE")


class ConfigError(Exception):
    """A required setting is missing; the process must not start half-configured."""


def create_app(env: Mapping[str, str] | None = None) -> RelayApp:
    env = os.environ if env is None else env
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise ConfigError("missing required settings: " + ", ".join(missing))
    db = env["RELAY_DB_PATH"]
    directory = Directory.load(env["RELAY_DIRECTORY_FILE"])
    return RelayApp(directory, TaskStore(db), TriageQueue(db), limiter=SharedRateLimiter(db))


_app: RelayApp | None = None


def application(environ: dict, start_response) -> Iterable[bytes]:
    """Build the app on the first request in each process (after the server forks), then reuse it."""
    global _app
    if _app is None:
        _app = create_app()
    return _app(environ, start_response)

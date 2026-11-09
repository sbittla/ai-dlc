"""Run Relay's HTTP service on the standard library's WSGI server.

    python -m relay.service --db relay.db --demo                 # demo users and tasks, port 8080
    python -m relay.service --db relay.db --directory users.json --port 9000

The server is single-threaded and binds to 127.0.0.1 unless told otherwise.
It is for development, tests and the book's labs; Chapter 11 puts the same
WSGI application behind a production server and a load balancer.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from wsgiref.simple_server import WSGIRequestHandler, make_server

from ..escalation import EscalationStore
from ..models import Task
from ..store import TaskStore
from ..worker import TriageQueue
from .app import RelayApp
from .directory import Directory, demo_directory

DEMO_TASKS = (
    Task(100, 10, "Scanner gateway offline", "open", date(2026, 11, 20), 3),
    Task(101, 10, "Replace label printer", "open", None, 4),
    Task(102, 11, "Quarterly stock count", "done", date(2026, 11, 30), 2),
)


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):  # one line per request, without the client address
        sys.stderr.write("%s\n" % (format % args))


def build_app(db: str, directory: Directory, demo: bool) -> RelayApp:
    tasks = TaskStore(db)
    if demo:
        existing = {t.id for p in directory.projects for t in tasks.by_project(p)}
        for t in DEMO_TASKS:
            if t.id not in existing:
                tasks.add(t)
    return RelayApp(directory, tasks, TriageQueue(db), escalation=EscalationStore(db))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m relay.service", description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="SQLite database file shared with the worker")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--directory", help="JSON file of users, projects and token hashes")
    src.add_argument("--demo", action="store_true", help="built-in demo users (tokens demo-owner ... demo-guest)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)
    if args.demo and args.host not in LOOPBACK:
        ap.error("--demo serves well-known demo tokens; it binds only to 127.0.0.1, ::1 or localhost")
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")

    directory = demo_directory() if args.demo else Directory.load(args.directory)
    app = build_app(args.db, directory, args.demo)
    with make_server(args.host, args.port, app, handler_class=QuietHandler) as httpd:
        sys.stderr.write(f"relay.service listening on http://{args.host}:{httpd.server_port}\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

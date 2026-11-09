"""Deploy-time schema migrations, run once as the migration role before the service and worker start (4.25.0; ADR-031).

    PYTHONPATH=src python -m relay.service.migrate --db relay.db

Every store in Relay creates its own tables when it opens a database, and the
escalation store also runs its schema migrations (ADR-019). In a deployment
that is the wrong place: the service and worker log in as roles that may read
and write rows but not change the schema (`infra/db/roles.sql`). So the
deployment runs this module first, as `relay_migrator`, and starts the
service and worker only if it exits 0 (`infra/runbooks/deploy.md`).

It opens each store once, which creates or migrates its tables, and copies
the legacy notification preferences into the new tables if that copy has not
run yet (ADR-018). It prints one JSON line describing what it found and did.
Like `relay.service.wsgi`, it refuses to run when `RELAY_DB_HOST` is set,
because this release has no PostgreSQL store adapter (ADR-014).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Mapping

from ..escalation import EscalationStore
from ..notify import NotifyStore, migrate_legacy
from ..store import TaskStore
from ..worker import TriageQueue
from .sharedlimit import SharedRateLimiter
from .wsgi import ADAPTER_MISSING, ConfigError


def run(db: str, env: Mapping[str, str] | None = None) -> dict:
    """Create or migrate every table in `db`. Returns a summary; raises on any refusal."""
    env = os.environ if env is None else env
    if env.get("RELAY_DB_HOST"):
        raise ConfigError(ADAPTER_MISSING)
    TaskStore(db)
    TriageQueue(db)
    SharedRateLimiter(db).close()
    escalation = EscalationStore(db)
    notify = NotifyStore(db)
    counts = notify.counts()
    legacy_rows = notify.conn.execute("SELECT COUNT(*) FROM notification_prefs").fetchone()[0]
    if counts["notify_optouts"] or counts["notify_spam_marks"]:
        copy = "already copied"
    elif legacy_rows == 0:
        copy = "nothing to copy"
    else:
        report = migrate_legacy(notify)
        copy = f"copied {report.legacy_users} legacy rows"
    esc_version = escalation.conn.execute("SELECT version FROM esc_schema").fetchone()[0]
    with sqlite3.connect(db) as conn:
        tables = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                             "AND name NOT LIKE 'sqlite_%'"))
    return {"esc_schema": esc_version, "notify_copy": copy, "tables": tables}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m relay.service.migrate", description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="the database file the service and worker share")
    args = ap.parse_args(argv)
    try:
        summary = run(args.db)
    except Exception as exc:  # noqa: BLE001 - any refusal stops the deployment
        sys.stderr.write(f"migration refused: {type(exc).__name__}: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(summary, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

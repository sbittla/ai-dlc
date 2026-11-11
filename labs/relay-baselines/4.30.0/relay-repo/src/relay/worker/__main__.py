"""Run the background worker.

    python -m relay.worker --db relay.db                 # poll until stopped (Ctrl+C)
    python -m relay.worker --db relay.db --drain         # process what is queued now, then exit
    python -m relay.worker --db relay.db --realtime      # wait out each simulated latency (load tests)
    python -m relay.worker --db relay.db --directory users.json --link-base https://relay.example/ws-1
                                                         # also run escalation passes (4.22.0, ADR-017)

No model is called: triage is simulated (relay/worker/triage.py). Escalation
passes need the workspace's projects, which the worker reads from the same
directory file the service uses; it reads only the `projects` list. Without
`--directory` the worker runs triage only, as before 4.22.0. Webhook events
need the workspace's secret, which this command does not take; the deployment
supplies it (Chapter 13).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..escalation import EngineConfig, EscalationStore
from ..models import Project
from ..store import TaskStore
from .escalation import EscalationPasses
from .queue import TriageQueue
from .runner import Worker
from .triage import SimulatedTriage


def load_projects(path: str) -> dict[int, Project]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {p["id"]: Project(p["id"], p["name"]) for p in data["projects"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m relay.worker", description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="SQLite database file shared with the service")
    ap.add_argument("--worker-id", default="worker-1")
    ap.add_argument("--drain", action="store_true", help="exit when nothing is available")
    ap.add_argument("--max-passes", type=int, default=None)
    ap.add_argument("--poll", type=float, default=1.0, help="seconds to sleep when idle")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--directory", help="JSON file of the workspace's users and projects; enables escalation passes")
    ap.add_argument("--link-base", default=None, help="web address for links in messages")
    args = ap.parse_args(argv)
    if args.directory and not args.link_base:
        ap.error("--directory needs --link-base, so that escalation messages link to the right workspace")

    passes = None
    if args.directory:
        passes = EscalationPasses(EscalationStore(args.db), TaskStore(args.db), load_projects(args.directory),
                                  EngineConfig(args.link_base))
    worker = Worker(TriageQueue(args.db), SimulatedTriage(), worker_id=args.worker_id, realtime=args.realtime,
                    escalation=passes)
    try:
        outcomes = worker.drain() if args.drain else worker.run(args.max_passes, args.poll)
    except KeyboardInterrupt:
        outcomes = dict(worker.outcomes)
    sys.stdout.write(json.dumps({"worker": args.worker_id, "outcomes": outcomes}, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

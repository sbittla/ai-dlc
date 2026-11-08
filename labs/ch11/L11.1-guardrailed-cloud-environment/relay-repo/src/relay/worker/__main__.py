"""Run the triage worker.

    python -m relay.worker --db relay.db                 # poll until stopped (Ctrl+C)
    python -m relay.worker --db relay.db --drain         # process what is queued now, then exit
    python -m relay.worker --db relay.db --realtime      # wait out each simulated latency (load tests)

No model is called: triage is simulated (relay/worker/triage.py).
"""

from __future__ import annotations

import argparse
import json
import sys

from .queue import TriageQueue
from .runner import Worker
from .triage import SimulatedTriage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m relay.worker", description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="SQLite database file shared with the service")
    ap.add_argument("--worker-id", default="worker-1")
    ap.add_argument("--drain", action="store_true", help="exit when nothing is available")
    ap.add_argument("--max-passes", type=int, default=None)
    ap.add_argument("--poll", type=float, default=1.0, help="seconds to sleep when idle")
    ap.add_argument("--realtime", action="store_true")
    args = ap.parse_args(argv)

    worker = Worker(TriageQueue(args.db), SimulatedTriage(), worker_id=args.worker_id, realtime=args.realtime)
    try:
        outcomes = worker.drain() if args.drain else worker.run(args.max_passes, args.poll)
    except KeyboardInterrupt:
        outcomes = dict(worker.outcomes)
    sys.stdout.write(json.dumps({"worker": args.worker_id, "outcomes": outcomes}, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

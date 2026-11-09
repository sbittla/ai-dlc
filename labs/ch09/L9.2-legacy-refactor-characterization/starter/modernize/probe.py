"""Characterize one candidate in a fresh interpreter, and print the result as JSON (provided).

    python -m modernize.probe --src <tree>/src --oracle ../data/relay-notify      # relay.notify from <tree>
    python -m modernize.probe --agent --oracle ../data/relay-notify               # the incident's rewrite

A fresh process matters: the legacy module and its rewrites keep a global
connection, and each integration step imports a different relay.notify.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from .charact import characterize


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modernize.probe")
    ap.add_argument("--src", type=Path)
    ap.add_argument("--agent", action="store_true")
    ap.add_argument("--oracle", type=Path, required=True)
    ap.add_argument("--accept", action="append", default=[])
    args = ap.parse_args(argv)
    sys.path.insert(0, str(args.oracle / "tests" / "notify"))
    legacy, corpus = importlib.import_module("legacy_reference"), importlib.import_module("corpus")
    if args.agent:
        sys.path.insert(0, str(args.oracle.parent / "agent-pr"))
        candidate = importlib.import_module("notifications_agent")
    else:
        sys.path.insert(0, str(args.src))
        candidate = importlib.import_module("relay.notify")
    r = characterize(candidate, legacy, corpus, set(args.accept))
    sys.stdout.write(json.dumps({"cases": r.cases, "decision_differences": r.decision_differences,
                                 "by_tag": dict(sorted(r.by_tag.items())), "prefs": dict(sorted(r.prefs.items())),
                                 "unaccepted_prefs": r.unaccepted_prefs, "shadow_differences": r.shadow_differences,
                                 "write_sequences": r.write_sequences, "write_differences": r.write_differences},
                                sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

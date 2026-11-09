"""Where Lab 9.2's inputs live, and how to import them (provided).

The oracle is Relay 4.22.0's frozen legacy module and corpus, copied into
data/relay-notify/ by scripts/generate_data.py. The candidates are the
incident's rewrite (data/agent-pr/) and Relay 4.22.0's relay.notify. Each
module that keeps a global connection is imported once per process; run
anything that needs a fresh copy through probe.py.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
ORACLE = DATA / "relay-notify"
AGENT = DATA / "agent-pr"


def use(*folders: Path) -> None:
    for folder in folders:
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))


def oracle_modules():
    """(legacy_reference, corpus) from the frozen copy in data/relay-notify/tests/notify/."""
    use(ORACLE / "tests" / "notify")
    return importlib.import_module("legacy_reference"), importlib.import_module("corpus")


def relay_notify(src: Path = ORACLE / "src"):
    use(src)
    return importlib.import_module("relay.notify")


def agent_module():
    use(AGENT)
    return importlib.import_module("notifications_agent")

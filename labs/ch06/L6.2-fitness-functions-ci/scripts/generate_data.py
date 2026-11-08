"""Write Lab 6.2's rules and seeded violations. Deterministic: byte-identical on every platform.

    python scripts/generate_data.py

`data/relay-repo/` is Relay 4.19.0's source, copied unchanged from Lab 6.1
(`src/`, `docs/adr/`, `pyproject.toml`); this script does not write it. It
reads it, and writes:

- `data/rules.json`: the fitness rules, each linked to the ADR it enforces;
- `data/seeded/<case>/`: overlay files that replace or add files in the clean
  tree, one seeded case per folder, and `data/seeded/manifest.json`, which says
  what each case should trigger. Two cases are known blind spots, seeded to
  measure them, and one is a control that should pass.
"""

from __future__ import annotations

import json
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
DATA = LAB / "data"
REPO = DATA / "relay-repo"

NETWORK = ["aiohttp", "asyncio", "ftplib", "http", "httpx", "requests", "smtplib", "socket", "socketserver",
           "ssl", "urllib", "urllib3", "wsgiref", "xmlrpc"]

DOMAIN = ["relay", "relay.api", "relay.duedates", "relay.models", "relay.roles", "relay.store", "relay.timezones"]

RULES = {
    "version": "relay-fitness-v1",
    "package": "relay",
    "patterns": "'x' matches module x; 'x.*' matches x and every module under it; 'x.+' only modules under x",
    "layers": [
        {"id": "FF001", "adr": "ADR-007", "name": "Domain modules depend on neither the service nor the worker",
         "from": DOMAIN, "forbid": ["relay.service.*", "relay.worker.*"]},
        {"id": "FF002", "adr": "ADR-007", "name": "The service uses only the worker's public interface",
         "from": ["relay.service.*"], "forbid": ["relay.worker.+"]},
        {"id": "FF003", "adr": "ADR-007", "name": "The worker does not depend on the service",
         "from": ["relay.worker.*"], "forbid": ["relay.service.*"]},
    ],
    "network": {"id": "FF004", "adr": "ADR-007", "name": "Only the service imports network modules",
                "allowed_in": ["relay.service.*"], "modules": NETWORK},
    "dependencies": {"id": "FF005", "adr": "ADR-008",
                     "name": "Every third-party import is declared in pyproject.toml and named by an accepted ADR",
                     "adr_dir": "docs/adr"},
    "cycles": {"id": "FF006", "adr": "ADR-007", "name": "No import cycles between Relay modules"},
}


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def after_imports(text: str, line: str) -> str:
    """Insert `line` after the module's last top-level import statement."""
    lines = text.split("\n")
    last = max(i for i, s in enumerate(lines) if s.startswith(("import ", "from ")))
    return "\n".join(lines[:last + 1] + [line] + lines[last + 1:])


API, APP, RUNNER, STORE = "src/relay/api.py", "src/relay/service/app.py", "src/relay/worker/runner.py", \
    "src/relay/store.py"
WORKER_IMPORT = "from ..worker import IdempotencyConflict, TriageQueue, is_stalled"

ADR_009 = """# ADR-009 — Use httpx for outbound HTTP from the service

Status: accepted
Date: 2026-12-01
Decided by: sam.o (architect of record)
Links: ESC-N09, CON-5
Dependency: httpx
Revisit when: the standard library's urllib meets the timeout and retry needs.

## Context

A seeded control case for Lab 6.2: a dependency that is declared and recorded.

## Options considered

### Option A — httpx, pinned

### Option B — urllib from the standard library

## Decision

Option A.

## Consequences

One new dependency, reviewed under Chapter 13's supply-chain rules.

## Rejected alternatives

### Option B — urllib from the standard library
Rejected because: it has no per-request connection pool or timeout split, which the webhook retries need.
"""

PYPROJECT_HTTPX = replace_once(read("pyproject.toml"), "dependencies = []  # standard library only",
                               'dependencies = ["httpx==0.28.1"]')


def cases() -> list[dict]:
    api, app, runner, store = read(API), read(APP), read(RUNNER), read(STORE)
    return [
        {"id": "V01", "title": "A domain module imports the worker", "expect": ["FF001"],
         "files": {API: after_imports(api, "from .worker import TriageQueue")}},
        {"id": "V02", "title": "The service imports a worker submodule", "expect": ["FF002"],
         "files": {APP: replace_once(app, WORKER_IMPORT,
                                     "from ..worker import is_stalled\n"
                                     "from ..worker.queue import IdempotencyConflict, TriageQueue")}},
        {"id": "V03", "title": "The worker imports the service, closing a cycle", "expect": ["FF003", "FF006"],
         "files": {RUNNER: after_imports(runner, "from ..service.app import job_view")}},
        {"id": "V04", "title": "The task store calls a web API", "expect": ["FF004"],
         "files": {STORE: after_imports(store, "import urllib.request")}},
        {"id": "V05", "title": "The service imports an undeclared package with no ADR", "expect": ["FF005"],
         "files": {APP: after_imports(app, "import requests")}},
        {"id": "V06", "title": "A declared package with no ADR", "expect": ["FF005"],
         "files": {APP: after_imports(app, "import httpx"), "pyproject.toml": PYPROJECT_HTTPX}},
        {"id": "V07", "title": "Control: a declared package with an accepted ADR", "expect": [],
         "files": {APP: after_imports(app, "import httpx"), "pyproject.toml": PYPROJECT_HTTPX,
                   "docs/adr/ADR-009-httpx.md": ADR_009}},
        {"id": "V08", "title": "A domain module imports worker internals dynamically", "expect": ["FF001"],
         "blind_spot": "importlib.import_module takes a string at run time; static analysis sees no import",
         "files": {API: after_imports(api, "import importlib") + "\n\n"
                   "def _queue():\n"
                   "    return importlib.import_module(\"relay.worker.queue\").TriageQueue\n"}},
        {"id": "V09", "title": "The task store reaches the network through a subprocess", "expect": ["FF004"],
         "blind_spot": "subprocess is not a network module; the call to curl is data, not an import",
         "files": {STORE: after_imports(store, "import subprocess") + "\n\n"
                   "def _ping() -> None:\n"
                   "    subprocess.run([\"curl\", \"-s\", \"https://example.com/\"], check=False)\n"}},
        {"id": "V10", "title": "A type-checking-only import of a worker submodule", "expect": ["FF002"],
         "note": "Flagged by design: no import at run time, but the service now depends on the queue's types",
         "files": {APP: after_imports(app, "from typing import TYPE_CHECKING\n"
                                           "if TYPE_CHECKING:\n"
                                           "    from ..worker.queue import Job")}},
    ]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> None:
    write(DATA / "rules.json", json.dumps(RULES, indent=2) + "\n")
    manifest = []
    for case in cases():
        for rel, text in case["files"].items():
            write(DATA / "seeded" / case["id"] / rel, text)
        entry = {k: v for k, v in case.items() if k != "files"}
        entry["files"] = sorted(case["files"])
        manifest.append(entry)
    write(DATA / "seeded" / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {DATA / 'rules.json'} and {len(manifest)} seeded cases")


if __name__ == "__main__":
    main()

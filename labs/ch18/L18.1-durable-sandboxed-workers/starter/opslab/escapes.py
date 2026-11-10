"""The escape attempts, run the pilot's way and in Relay 4.30.0's sandbox. TODO 4 is `classify`.

The pilot ran the agent's code in a child process of the worker, with the worker's environment and no policy.
`run_attempt` runs each attempt in `data/escapes.json` both ways, in a fresh folder holding a stand-in secrets
file and a stand-in copy of Relay's database beside the working directory, with a TCP listener on 127.0.0.1
standing in for an internal service. The environment holds a stand-in payments key. Nothing leaves the machine:
the attempts that would (the metadata address, an outside name) run only in the sandbox, which refuses them
before any packet is sent.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
from contextlib import contextmanager

from . import DATA
from relay.agentops.sandbox import SandboxPolicy, run_code

POLICY = SandboxPolicy(timeout_s=3, max_output_bytes=64_000)


def load() -> dict:
    return json.loads((DATA / "escapes.json").read_text(encoding="utf-8"))


@contextmanager
def internal_service():
    """A listener on 127.0.0.1 that accepts and closes connections: the stand-in for an internal service."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def serve():
        try:
            while True:
                srv.accept()[0].close()
        except OSError:
            pass
    threading.Thread(target=serve, daemon=True).start()
    try:
        yield srv.getsockname()[1]
    finally:
        srv.close()


def _code(attempt: dict, port: int) -> str:
    return attempt["code"].replace("{port}", str(port))


def run_attempt(attempt: dict, mode: str, port: int) -> dict:
    """Run one attempt `mode` = "pilot" or "sandbox". Returns status, stdout, refusals."""
    import shutil
    import tempfile
    from pathlib import Path

    data = load()
    files = {"invoice.json": json.dumps([{"line": "seats", "amount": 180}, {"line": "seats", "amount": 180}])}
    code = _code(attempt, port)
    if mode == "sandbox":
        result = run_code(code, files, POLICY)
    else:
        # The pilot's folder layout: secrets and the database sit beside the working directory, and the run
        # inherits an environment with the payments key. run_code(unrestricted=True) uses its own temporary
        # folder, so the lab writes the "outside" files where that folder's parent will be.
        base = Path(tempfile.mkdtemp(prefix="lab18-pilot-"))
        try:
            outside = base / "outside"
            outside.mkdir()
            (outside / "secrets.env").write_text("RELAY_PAYMENTS_KEY=rk_lab_not_a_real_key\n", encoding="utf-8")
            db = sqlite3.connect(outside / "relay.db")
            db.execute("CREATE TABLE tasks (id INTEGER)")
            db.execute("INSERT INTO tasks VALUES (1)")
            db.commit()
            db.close()
            env = dict(os.environ)
            env[data["secret_env"]["name"]] = data["secret_env"]["value"]
            result = _run_pilot(code, files, base, env)
        finally:
            shutil.rmtree(base, ignore_errors=True)
    return {"status": result.status, "stdout": result.stdout.strip().splitlines()[-1:] or [""],
            "refusals": [r["reason"] for r in result.refusals]}


def _run_pilot(code: str, files: dict, base, env: dict):
    """Run `code` in `base`/work the pilot's way: a child process with the given environment and no policy."""
    import subprocess
    import sys
    import time

    from relay.agentops.sandbox import SandboxResult
    work = base / "work"
    work.mkdir()
    for name, text in files.items():
        (work / name).write_text(text, encoding="utf-8")
    (work / "main.py").write_text(code, encoding="utf-8")
    started = time.monotonic()
    try:
        proc = subprocess.run([sys.executable, "-B", "main.py"], cwd=work, env=env, capture_output=True,
                              text=True, timeout=POLICY.timeout_s)
        status = "ok" if proc.returncode == 0 else "error"
        return SandboxResult(status, proc.returncode, proc.stdout, proc.stderr, (), time.monotonic() - started)
    except subprocess.TimeoutExpired:
        return SandboxResult("timeout", None, "", "", (), POLICY.timeout_s)


def classify(observation: dict) -> str:
    """TODO 4. Name what one attempt achieved, from its observation {status, stdout, refusals}.

    - "refused"  if the sandbox recorded at least one refusal;
    - "stopped"  if the run hit the timeout or the output cap (status "timeout" or "output_limit");
    - "reached"  if the attempt printed "got" (it read, wrote, connected or started what it tried to);
    - "nothing"  if it printed "none" (it ran, and what it looked for was not there);
    - "ok"       if it ran and printed anything else (the legitimate attempt's answer);
    - "error"    otherwise.
    Check them in that order.
    """
    raise NotImplementedError("TODO 4")


def run_all() -> list[dict]:
    rows = []
    with internal_service() as port:
        for attempt in load()["attempts"]:
            sandbox = run_attempt(attempt, "sandbox", port)
            pilot = run_attempt(attempt, "pilot", port) if attempt["pilot"] else None
            rows.append({"id": attempt["id"], "what": attempt["what"],
                         "pilot": classify(pilot) if pilot else "not run",
                         "sandbox": classify(sandbox), "refusal": (sandbox["refusals"] or ["-"])[-1],
                         "sandbox_stdout": sandbox["stdout"][-1][:40]})
    return rows

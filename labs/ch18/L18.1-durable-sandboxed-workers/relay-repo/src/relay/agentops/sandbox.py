"""Run code an agent wrote, in a separate, locked-down process (added in 4.30.0; ADR-050).

Agent-written code, such as the tests a coding agent runs, is untrusted: a steered agent can write anything.
It must never run inside the worker's own process or container, where the worker's credentials, database
and network are. `run_code` runs it in a fresh interpreter with:

- **its own process**, started in isolated mode (`-I -S -B`), so no environment variable, user site or
  path entry of the worker's reaches it;
- **an empty environment** (on Windows, only SYSTEMROOT, which the interpreter needs to start), so no secret
  in the worker's environment can be read;
- **a throwaway working directory** holding only the files the call passes in; reads elsewhere are limited
  to the interpreter's own library, and writes elsewhere are refused;
- **no network** unless the policy allows exact (host, port) pairs, which in Relay's deployment is only the
  egress proxy;
- **no processes and no native code it knows of**: starting a process or a shell, ctypes and cffi under any
  name, SQLite (which opens files below the hook's view), Windows file APIs, and frame and collector
  introspection are refused;
- **limits**: a wall-clock timeout that kills the process, a cap on the output kept, and on POSIX systems
  CPU time, memory, file size and open files (resource limits). Windows has no portable equivalent in the
  standard library, so there the timeout and the output cap are the only limits.

The refusals come from an audit hook (`relay.agentops.sandbox_child`), which reports each one over the child's
standard output, a pipe this process reads; the agent's own output goes to a file. Code can add records to the
pipe but cannot erase one already sent, and code that closes or replaces the channel ends the child with exit
status 86, recorded as `refused:report-channel`.

**This local layer is a policy check and a no-secrets environment, not containment.** An audit hook runs inside
the process it watches (PEP 578), and code that reaches native memory by a path the policy does not know gets
past it. Run it only where nothing worth stealing is reachable: Chapter 3's dev container or an ephemeral CI
runner with no credentials. In the cloud the boundary is ADR-050's sandbox runner, its own task with no task role
and no outbound network (designed, not built in 4.30.0). A microVM or a user-space kernel adds a kernel boundary.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .sandbox_child import _norm

CHILD = Path(__file__).with_name("sandbox_child.py")
STATUSES = ("ok", "error", "timeout", "output_limit")
TAMPERED_EXIT = 86


@dataclass(frozen=True)
class SandboxPolicy:
    timeout_s: float = 30.0
    max_output_bytes: int = 64_000
    allow_net: tuple[tuple[str, int], ...] = ()  # exact (host, port) pairs; empty means no network at all
    cpu_seconds: int = 60                        # POSIX only
    memory_bytes: int = 1_024 * 1_024 * 1_024    # POSIX only (address space)
    file_bytes: int = 16 * 1_024 * 1_024         # POSIX only (largest file the code may write)
    open_files: int = 64                         # POSIX only

    def __post_init__(self) -> None:
        if self.timeout_s <= 0 or self.max_output_bytes <= 0:
            raise ValueError("timeout and output cap must be positive")
        for host, port in self.allow_net:
            if not host or "*" in host or not 0 < int(port) < 65536:
                raise ValueError("network allowlist entries must be an exact host and port")


@dataclass(frozen=True)
class SandboxResult:
    status: str                      # ok, error, timeout, output_limit
    exit_code: int | None
    stdout: str
    stderr: str
    refusals: tuple[dict, ...] = field(default_factory=tuple)
    seconds: float = 0.0

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


def child_env() -> dict[str, str]:
    """The child's whole environment: nothing, except what Windows needs to start an interpreter."""
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        return {"SYSTEMROOT": os.environ["SYSTEMROOT"]}
    return {}


def _limits(policy: SandboxPolicy):
    if os.name != "posix":
        return None

    def apply() -> None:  # runs in the child between fork and exec
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (policy.file_bytes, policy.file_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (policy.open_files, policy.open_files))
    return apply


def _read_capped(path: Path, cap: int) -> tuple[str, bool]:
    with path.open("rb") as f:
        data = f.read(cap + 1)
    return data[:cap].decode("utf-8", errors="replace"), len(data) > cap


def _wait(proc: subprocess.Popen, timeout_s: float) -> tuple[bytes, bool]:
    """Wait for the child, reading the report pipe as it goes; kill it at the timeout. Returns (report, timed_out)."""
    try:
        report, _ = proc.communicate(timeout=timeout_s)
        return report or b"", False
    except subprocess.TimeoutExpired:
        proc.kill()
        report, _ = proc.communicate()
        return report or b"", True


def _parse_report(data: bytes) -> list[dict]:
    """The child's refusal records, one JSON object per line. A line that is not one is kept as a refusal too:
    only the agent's code could have written it, and an unexplained record is never silently dropped."""
    out = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or not str(record.get("reason", "")).startswith("refused:"):
                raise ValueError(line)
        except ValueError:
            record = {"event": "unparsable", "reason": "refused:unparsable-report"}
        out.append(record)
    return out


def run_code(code: str, files: dict[str, str] | None = None, policy: SandboxPolicy | None = None,
             unrestricted: bool = False, env: dict[str, str] | None = None) -> SandboxResult:
    """Run `code` as `main.py` with `files` beside it, under `policy`.

    `unrestricted=True` runs the same code the way Relay's pilot did, for comparison in the labs only: the
    caller's environment (or `env`), no audit hook, no resource limits. Never use it for an agent's code.
    """
    import time

    policy = policy or SandboxPolicy()
    base = Path(tempfile.mkdtemp(prefix="relay-sbx-")).resolve()
    work, private = base / "work", base / "private"
    work.mkdir()
    private.mkdir()
    try:
        for name, text in (files or {}).items():
            target = (work / name).resolve()
            if work.resolve() not in target.parents:
                raise ValueError(f"file {name!r} would be written outside the working directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        (work / "main.py").write_text(code, encoding="utf-8", newline="\n")
        out_path, err_path = private / "stdout", private / "stderr"
        if unrestricted:
            argv = [sys.executable, "-B", str(work / "main.py")]
            child_environment = dict(os.environ if env is None else env)
            preexec = None
        else:
            spec = {"workdir": _norm(str(work)), "allow_net": [list(p) for p in policy.allow_net]}
            argv = [sys.executable, "-I", "-S", "-B", str(CHILD), json.dumps(spec), str(out_path)]
            child_environment = child_env()
            preexec = _limits(policy)
        started = time.monotonic()
        with err_path.open("wb") as err:
            if unrestricted:
                with out_path.open("wb") as out:
                    proc = subprocess.Popen(argv, cwd=str(work), env=child_environment, stdin=subprocess.DEVNULL,
                                            stdout=out, stderr=err, close_fds=True)
                    report, timed_out = _wait(proc, policy.timeout_s)
            else:
                proc = subprocess.Popen(argv, cwd=str(work), env=child_environment, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=err, preexec_fn=preexec, close_fds=True,
                                        start_new_session=(os.name == "posix"))
                report, timed_out = _wait(proc, policy.timeout_s)
        exit_code = None if timed_out else proc.returncode
        seconds = time.monotonic() - started
        stdout, over_out = _read_capped(out_path, policy.max_output_bytes) if out_path.exists() else ("", False)
        stderr, over_err = _read_capped(err_path, policy.max_output_bytes)
        refusals = [] if unrestricted else _parse_report(report)
        if exit_code == TAMPERED_EXIT and not unrestricted:
            refusals.append({"event": "report-channel", "reason": "refused:report-channel"})
        refusals = tuple(refusals)
        if timed_out:
            status = "timeout"
        elif over_out or over_err:
            status = "output_limit"
        else:
            status = "ok" if exit_code == 0 else "error"
        return SandboxResult(status, exit_code, stdout, stderr, refusals, round(seconds, 3))
    finally:
        shutil.rmtree(base, ignore_errors=True)

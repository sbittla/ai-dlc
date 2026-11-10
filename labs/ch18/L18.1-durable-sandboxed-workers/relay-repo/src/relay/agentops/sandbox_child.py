"""The code that runs inside the local sandbox's child process, before the agent's code (4.30.0; ADR-050).

`relay.agentops.sandbox` starts a fresh interpreter in isolated mode (`-I -S -B`) on this file, in an empty
working directory, with an empty environment. This file then:

1. reads the policy from its command line (nothing in it is secret) and freezes it into immutable values;
2. keeps the process's standard output, a pipe to the parent, as the **report channel**, and points the agent's
   standard output at a file instead;
3. installs an audit hook (PEP 578) that refuses, by raising PermissionError, every event outside the policy, and
   reports each refusal to the parent over the pipe before raising;
4. drops every local reference to the hook and the policy, replaces `__main__`, and runs the agent's `main.py`.

**This is a policy check, not a security boundary.** An audit hook runs inside the process it watches. PEP 578
says so, and the round-1 review of this module showed why: agent code reached the hook's policy through frames
and the garbage collector, loaded ctypes' C core under another name, and used SQLite to read and write files the
`open` check never sees. Those paths are now refused (frame and collector introspection, native modules judged
by file as well as name, SQLite as a whole, Windows file APIs, truncating a descriptor), and refusals go to a
pipe the parent reads, so code can add records but cannot erase one already sent. Code that tampers with the
channel itself ends the process with exit status 86, which the parent records.

What remains possible in pure Python is unknown, not zero; code that reaches native memory through a path not
listed here gets past the hook entirely. So agent code runs locally only in Chapter 3's dev container or an
ephemeral CI runner with no credentials, and in the cloud only in the sandbox runner of ADR-050: its own task,
with no task role and no outbound network. That task, not this file, is the boundary.

`decide` is pure, so the policy is tested directly as well as through real processes. Standard library only, and
nothing from Relay: the child runs with no `relay` on its path.
"""

from __future__ import annotations

import io
import json
import os
import sys
import types
from collections import namedtuple

PROCESS_EVENTS = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
                            "os.forkpty", "os.startfile", "os.kill", "os.killpg", "pty.spawn", "webbrowser.open"})
# Modules that reach native memory, start processes or open files below the audit hook's view. Judged by every
# component of the module's name and by the file an extension module is loaded from.
NATIVE_MODULES = frozenset({"ctypes", "_ctypes", "cffi", "_cffi_backend", "_posixsubprocess", "sqlite3",
                            "_sqlite3"})
INTROSPECTION_EVENTS = frozenset({"gc.get_objects", "gc.get_referrers", "gc.get_referents", "sys._current_frames",
                                  "sys._current_exceptions", "sys.settrace", "sys.setprofile", "sys.addaudithook",
                                  "sys.monitoring.register_callback", "sys.remote_exec"})
FRAME_ATTRIBUTES = frozenset({"tb_frame", "gi_frame", "cr_frame", "ag_frame"})
EXTENSION_SUFFIXES = (".pyd", ".so", ".dll", ".dylib")
NETWORK_PREFIXES = ("http.client.", "smtplib.", "ftplib.", "imaplib.", "poplib.", "nntplib.", "telnetlib.",
                    "urllib.")
NATIVE_PREFIXES = ("_winapi.", "msvcrt.", "winreg.", "ctypes.", "sqlite3.", "mmap.")
PATH_EVENTS = types.MappingProxyType({  # event -> (indexes of path arguments, writes?)
    "os.listdir": ((0,), False), "os.scandir": ((0,), False), "glob.glob": ((0,), False),
    "os.chdir": ((0,), False), "os.remove": ((0,), True), "os.rmdir": ((0,), True), "os.mkdir": ((0,), True),
    "os.rename": ((0, 1), True), "os.chmod": ((0,), True), "os.chown": ((0,), True), "os.utime": ((0,), True),
    "os.truncate": ((0,), True), "shutil.copyfile": ((0, 1), True), "shutil.copytree": ((0, 1), True),
    "shutil.move": ((0, 1), True), "shutil.rmtree": ((0,), True), "shutil.make_archive": ((0,), True),
    "shutil.unpack_archive": ((0, 1), True),
})
ALWAYS_REFUSED = frozenset({"os.symlink", "os.link", "os.add_dll_directory"})
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
TAMPERED_EXIT = 86

Policy = namedtuple("Policy", "workdir read_roots allow_net")


def _norm(path) -> str | None:
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, str):
        return None
    return os.path.normcase(os.path.abspath(path))


def make_policy(workdir: str, read_roots, allow_net) -> Policy:
    """An immutable policy: normalised paths in tuples, network pairs in a frozenset."""
    work = _norm(workdir)
    return Policy(work, tuple(sorted({_norm(r) for r in read_roots} - {work})),
                  frozenset((str(h), int(p)) for h, p in allow_net))


def _inside(path: str, roots) -> bool:
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def _native_import(args: tuple, read_roots) -> str | None:
    name = str(args[0]) if args else ""
    hit = next((part for part in name.split(".") if part in NATIVE_MODULES), None)
    if hit:
        return f"refused:import:{hit}"
    filename = args[1] if len(args) > 1 else None
    if isinstance(filename, (str, bytes)):
        path = _norm(filename) or ""
        base = os.path.basename(path)
        if any(base.startswith(stem.lower()) for stem in NATIVE_MODULES):
            return "refused:import:native"
        if path.endswith(EXTENSION_SUFFIXES) and not _inside(path, read_roots):
            return "refused:import:native"
    return None


def decide(event: str, args: tuple, policy: Policy) -> str | None:
    """None to allow `event`, or the reason it is refused."""
    workdir, read_roots = policy.workdir, (policy.workdir, *policy.read_roots)
    if event in ALWAYS_REFUSED:
        return f"refused:{event}"
    if event in PROCESS_EVENTS:
        return "refused:process"
    if event in INTROSPECTION_EVENTS:
        return "refused:introspection"
    if event == "object.__getattr__":
        return "refused:introspection" if len(args) > 1 and args[1] in FRAME_ATTRIBUTES else None
    if event == "import":
        return _native_import(args, policy.read_roots)
    if event.startswith(NATIVE_PREFIXES):
        return "refused:native"
    if event.startswith(NETWORK_PREFIXES):
        return "refused:network"
    if event.startswith("socket."):
        if event == "socket.__new__":
            return None if policy.allow_net else "refused:network"
        if event in ("socket.connect", "socket.getaddrinfo"):
            target = args[1] if event == "socket.connect" else (args[0], args[1])
            if isinstance(target, tuple) and len(target) >= 2:
                host = target[0].decode() if isinstance(target[0], bytes) else target[0]
                try:
                    if (host, int(target[1])) in policy.allow_net:
                        return None
                except (TypeError, ValueError):
                    pass
            return "refused:network"
        return "refused:network"  # bind, sendto, sendmsg, gethostbyname, gethostbyaddr, getnameinfo, ...
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if isinstance(path, int):
            return None if path in (0, 1, 2) else "refused:open:descriptor"
        norm = _norm(path)
        if norm is None:
            return "refused:open"
        writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and bool(flags & WRITE_FLAGS))
        if _inside(norm, [workdir]):
            return None
        if not writes and _inside(norm, read_roots):
            return None
        return "refused:open:write" if writes else "refused:open:read"
    if event in PATH_EVENTS:
        indexes, writes = PATH_EVENTS[event]
        for i in indexes:
            value = args[i] if i < len(args) else None
            if isinstance(value, int):
                if writes:
                    return f"refused:{event}:descriptor"
                continue
            if value is None:
                if event in ("os.listdir", "os.scandir"):
                    value = "."
                else:
                    continue
            norm = _norm(value)
            roots = [workdir] if writes else read_roots
            if norm is None or not _inside(norm, roots):
                return f"refused:{event}"
        return None
    return None


def _install(policy: Policy, report_fd: int) -> None:
    """Install the hook. The policy and the report channel live only in this closure, as immutable values."""
    expected = os.fstat(report_fd)
    identity = (expected.st_mode, expected.st_ino, expected.st_dev)

    def hook(event, args, _decide=decide, _policy=policy, _fd=report_fd, _identity=identity, _fstat=os.fstat,
             _write=os.write, _exit=os._exit, _dumps=json.dumps, _busy=[False]):
        if _busy[0]:
            return
        _busy[0] = True
        try:
            reason = _decide(event, args, _policy)
        finally:
            _busy[0] = False
        if reason is None:
            return
        try:
            st = _fstat(_fd)
            if (st.st_mode, st.st_ino, st.st_dev) != _identity:
                _exit(TAMPERED_EXIT)  # the channel was closed or replaced: no refusal may go unrecorded
            _write(_fd, (_dumps({"event": event, "reason": reason}) + "\n").encode("utf-8"))
        except OSError:
            _exit(TAMPERED_EXIT)
        raise PermissionError(f"sandbox {reason}")

    sys.addaudithook(hook)


def _execute(code, namespace: dict) -> None:
    exec(code, namespace)  # noqa: S102 - the sandbox's purpose: run the agent's code under the hook


def main(argv: list[str]) -> int:
    spec = json.loads(argv[1])
    out_path = argv[2]
    workdir = _norm(spec["workdir"])
    os.chdir(workdir)
    sys.stdout.flush()
    report_fd = os.dup(1)
    out_fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.dup2(out_fd, 1)
    os.close(out_fd)
    sys.stdout = io.TextIOWrapper(io.FileIO(1, "w", closefd=False), encoding="utf-8", line_buffering=True)
    sys.path[:] = [p for p in sys.path if p and _norm(p) != workdir] + [workdir]
    # Readable outside the working directory: the interpreter's own library, and this file (for tracebacks).
    roots = [p for p in sys.path if p and os.path.exists(p)] + [__file__]
    policy = make_policy(workdir, roots, spec.get("allow_net", []))
    with open(os.path.join(workdir, "main.py"), encoding="utf-8") as f:
        code = compile(f.read(), "main.py", "exec")
    _install(policy, report_fd)
    del policy, spec, roots, report_fd
    module = types.ModuleType("__main__")
    module.__file__ = "main.py"
    sys.modules["__main__"] = module
    try:
        _execute(code, module.__dict__)
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - reported without walking frames, which the policy refuses
        tb, line = exc.__traceback__, None
        while tb is not None:
            line, tb = tb.tb_lineno, tb.tb_next
        sys.stdout.flush()
        sys.stderr.write(f"main.py, last line run: {line}\n{type(exc).__name__}: {exc}\n")
        return 1
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

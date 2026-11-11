"""The code that runs inside the local sandbox's child process, before the agent's code (4.30.0; ADR-050).

`relay.agentops.sandbox` starts a fresh interpreter in isolated mode (`-I -S -B`) on this file, in an empty
working directory, with an empty environment. This file then:

1. reads the policy from its command line (nothing in it is secret) and freezes it into immutable values;
2. keeps the process's standard output, a pipe to the parent, as the **report channel**, and points the agent's
   standard output at a file instead;
3. installs an audit hook (PEP 578) that refuses, by raising PermissionError, every event outside the policy, and
   reports each refusal to the parent over the pipe before raising;
4. replaces `__main__` and runs the agent's `main.py`.

**This is a tripwire, not a security boundary.** An audit hook runs inside the process it watches; PEP 578 says
so, and code in the same process can reach and change the hook's own state. Reviews found several ways; the
measures below close the simpler ones, and each of those probes is now a test:

- The rules are not module globals. `_build_decide` captures every table and every function it uses (C functions
  only, such as `os.getcwd`, never a Python helper the agent could rebind) in a closure, so rebinding this
  module's globals, `os.path` or `json` from agent code changes nothing the hook reads.
- The hook never runs agent code. It accepts only exact `str`, `bytes` and `int` arguments where it reads paths,
  hosts or names; a subclass, or an object with `__fspath__`, is refused before any of its methods could run.
  Any audit event raised while the hook is deciding is refused, not skipped.
- Introspection that reaches live state is refused: the garbage collector (every route to the hook's closure
  cells), trace and profile functions, and `tb_frame` and `gi_frame`. `sys._getframe` and `f_back` stay allowed,
  because the standard library needs them (`collections.namedtuple` on 3.11). The hook holds plain copies of the
  policy's values and of every builtin it calls, and this module's globals are cleared before the agent's code
  runs. That does not make the hook unreachable: a finalizer run by the collector while the hook is working can
  resume a generator whose frame leads to the hook's own frame (Lab 18.1's E21), and from there its rules.
- Refusals go to the parent over a pipe that the code can add to but not take back; closing or replacing it ends
  the process with exit status 86.

What remains possible is known not to be zero: E21 gets past the hook in pure Python, code that reaches native
memory gets past it entirely, and some actions raise no event at all. So agent code runs locally only in Chapter 3's dev
container or an ephemeral CI runner with no credentials, and in the cloud only in ADR-050's sandbox runner: its
own task, with no task role and no outbound network. That task, not this file, is the boundary.

Standard library only, and nothing from Relay: the child runs with no `relay` on its path.
"""

from __future__ import annotations

import io
import json
import os
import sys
import types
from collections import namedtuple

TAMPERED_EXIT = 86
SELF = __file__
Policy = namedtuple("Policy", "workdir read_roots allow_net")


def _build_decide():
    """Return `decide(event, args, policy)`, with every table and helper captured here, not looked up later."""
    process_events = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
                                "os.fork", "os.forkpty", "os.startfile", "os.kill", "os.killpg", "pty.spawn",
                                "webbrowser.open"})
    native_modules = frozenset({"ctypes", "_ctypes", "cffi", "_cffi_backend", "_posixsubprocess", "sqlite3",
                                "_sqlite3"})
    introspection = frozenset({"gc.get_objects", "gc.get_referrers", "gc.get_referents", "sys._current_frames",
                               "sys._current_exceptions", "sys.settrace", "sys.setprofile", "sys.addaudithook",
                               "sys.monitoring.register_callback", "sys.remote_exec"})
    frame_attributes = frozenset({"tb_frame", "gi_frame", "cr_frame", "ag_frame"})
    extension_suffixes = (".pyd", ".so", ".dll", ".dylib")
    network_prefixes = ("http.client.", "smtplib.", "ftplib.", "imaplib.", "poplib.", "nntplib.", "telnetlib.",
                        "urllib.")
    native_prefixes = ("_winapi.", "msvcrt.", "winreg.", "ctypes.", "sqlite3.", "mmap.")
    path_events = {"os.listdir": ((0,), False), "os.scandir": ((0,), False), "glob.glob": ((0,), False),
                   "os.chdir": ((0,), False), "os.remove": ((0,), True), "os.rmdir": ((0,), True),
                   "os.mkdir": ((0,), True), "os.rename": ((0, 1), True), "os.chmod": ((0,), True),
                   "os.chown": ((0,), True), "os.utime": ((0,), True), "os.truncate": ((0,), True),
                   "shutil.copyfile": ((0, 1), True), "shutil.copytree": ((0, 1), True),
                   "shutil.move": ((0, 1), True), "shutil.rmtree": ((0,), True),
                   "shutil.make_archive": ((0,), True), "shutil.unpack_archive": ((0, 1), True)}
    always_refused = frozenset({"os.symlink", "os.link", "os.add_dll_directory"})
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    windows = os.name == "nt"
    sep = "\\" if windows else "/"
    getcwd = os.getcwd
    fullpath = None
    if windows:
        import nt
        fullpath = nt._getfullpathname
    encoding = sys.getfilesystemencoding()
    _str, _bytes, _int, _tuple, _type = str, bytes, int, tuple, type
    _len, _bool = len, bool  # builtins are captured too: agent code can rebind builtins.len

    def norm(path):
        """An absolute, normalised path from an exact str or bytes, using only C functions; None otherwise."""
        if _type(path) is _bytes:
            path = _bytes.decode(path, encoding, "surrogateescape")
        if _type(path) is not _str or "\x00" in path:
            return None
        if windows:
            return _str.lower(fullpath(path))
        if not path.startswith("/"):
            path = getcwd() + "/" + path
        parts = []
        for part in path.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)
        return "/" + "/".join(parts)

    def inside(path, roots):
        for root in roots:
            if path == root or path.startswith(root.rstrip(sep) + sep):
                return True
        return False

    def native_import(args, read_roots):
        if not args or _type(args[0]) is not _str:
            return "refused:import:name"
        hit = None
        for part in args[0].split("."):
            if part in native_modules:
                hit = part
                break
        if hit:
            return "refused:import:" + hit
        filename = args[1] if _len(args) > 1 else None
        if filename is None:
            return None
        path = norm(filename)
        if path is None:
            return "refused:import:file"
        base = path.rsplit(sep, 1)[-1]
        for stem in native_modules:
            if base.startswith(stem):
                return "refused:import:native"
        if path.endswith(extension_suffixes) and not inside(path, read_roots):
            return "refused:import:native"
        return None

    def rule(event, args, workdir, read_roots, allow_net):
        """None to allow `event`, or the reason it is refused. Every input is a plain str, tuple or frozenset."""
        roots = (workdir, *read_roots)
        if event in always_refused:
            return "refused:" + event
        if event in process_events:
            return "refused:process"
        if event in introspection:
            return "refused:introspection"
        if event == "object.__getattr__":
            name = args[1] if _len(args) > 1 else None
            if _type(name) is not _str or name in frame_attributes:
                return "refused:introspection"
            return None
        if event == "import":
            return native_import(args, read_roots)
        if event.startswith(native_prefixes):
            return "refused:native"
        if event.startswith(network_prefixes):
            return "refused:network"
        if event.startswith("socket."):
            if event == "socket.__new__":
                return None if allow_net else "refused:network"
            if event in ("socket.connect", "socket.getaddrinfo"):
                target = args[1] if event == "socket.connect" else (args[0], args[1])
                if _type(target) is _tuple and _len(target) >= 2:
                    host, port = target[0], target[1]
                    if _type(host) is _bytes:
                        host = _bytes.decode(host, "ascii", "replace")
                    if _type(host) is _str and _type(port) is _int and (host, port) in allow_net:
                        return None
            return "refused:network"
        if event == "open":
            path = args[0] if args else None
            mode = args[1] if _len(args) > 1 else None
            flags = args[2] if _len(args) > 2 else None
            if _type(path) is _int:
                return None if path in (0, 1, 2) else "refused:open:descriptor"
            where = norm(path)
            if where is None:
                return "refused:open:path-type"
            writes = (_type(mode) is _str and ("w" in mode or "a" in mode or "x" in mode or "+" in mode)) or (
                _type(flags) is _int and _bool(flags & write_flags))
            if inside(where, (workdir,)):
                return None
            if not writes and inside(where, roots):
                return None
            return "refused:open:write" if writes else "refused:open:read"
        if event in path_events:
            indexes, writes = path_events[event]
            for i in indexes:
                value = args[i] if i < _len(args) else None
                if _type(value) is _int:
                    if writes:
                        return "refused:" + event + ":descriptor"
                    continue
                if value is None:
                    if event in ("os.listdir", "os.scandir"):
                        value = "."
                    else:
                        continue
                where = norm(value)
                if where is None or not inside(where, (workdir,) if writes else roots):
                    return "refused:" + event
            return None
        return None

    def make_policy(workdir, read_roots, allow_net):
        work = norm(workdir)
        others = sorted({norm(r) for r in read_roots} - {work, None})
        return Policy(work, _tuple(others), frozenset((_str(h), _int(p)) for h, p in allow_net))

    def decide(event, args, policy):
        """The rules over a Policy, for tests. The hook never calls this: it holds the policy's values themselves."""
        return rule(event, args, policy.workdir, policy.read_roots, policy.allow_net)

    return decide, make_policy, rule


decide, make_policy, _ = _build_decide()  # for tests; the hook builds its own copy in `_install`


def _install(spec_workdir: str, roots: list, allow_net: list, report_fd: int) -> None:
    """Install the hook. Its rules, its policy and the report channel live only in this closure."""
    _decide, _make, _rule = _build_decide()
    policy = _make(spec_workdir, roots, allow_net)
    # Plain values, copied out of the Policy: an exact str, a tuple of exact strs and a frozenset of (str, int).
    # Nothing the agent can reach (the Policy class, this module's globals) is read again after this point.
    workdir, read_roots = str(policy.workdir), tuple(str(r) for r in policy.read_roots)
    net = frozenset((str(h), int(p)) for h, p in policy.allow_net)
    del policy, _decide, _make
    expected = os.fstat(report_fd)
    identity = (expected.st_mode, expected.st_ino, expected.st_dev)

    def hook(event, args, _rule=_rule, _w=workdir, _roots=read_roots, _net=net, _fd=report_fd, _identity=identity,
             _fstat=os.fstat,
             _write=os.write, _exit=os._exit, _str=str, _type=type, _refused=PermissionError, _tampered=TAMPERED_EXIT,
             _busy=[False]):
        if _busy[0]:  # an event raised while deciding could only come from code the hook did not expect
            reason = "refused:reentrant"
        else:
            _busy[0] = True
            try:
                reason = _rule(event, args, _w, _roots, _net)
            except Exception:  # noqa: BLE001 - a rule that cannot decide refuses
                reason = "refused:undecidable"
            finally:
                _busy[0] = False
        if reason is None:
            return
        name = event if _type(event) is _str else "?"
        line = '{"event": "%s", "reason": "%s"}\n' % (name.replace('"', "'"), reason)
        try:
            st = _fstat(_fd)
            if (st.st_mode, st.st_ino, st.st_dev) != _identity:
                _exit(_tampered)  # the channel was closed or replaced: no refusal may go unrecorded
            _write(_fd, line.encode("utf-8"))
        except OSError:
            _exit(_tampered)
        raise _refused("sandbox " + reason)

    sys.addaudithook(hook)


def _execute(code, namespace: dict) -> None:
    exec(code, namespace)  # noqa: S102 - the sandbox's purpose: run the agent's code under the hook


def main(argv: list[str]) -> int:
    spec = json.loads(argv[1])
    out_path = argv[2]
    workdir = os.path.normcase(os.path.abspath(spec["workdir"]))
    os.chdir(workdir)
    sys.stdout.flush()
    report_fd = os.dup(1)
    out_fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.dup2(out_fd, 1)
    os.close(out_fd)
    sys.stdout = io.TextIOWrapper(io.FileIO(1, "w", closefd=False), encoding="utf-8", line_buffering=True)
    sys.path[:] = [p for p in sys.path if p and os.path.normcase(os.path.abspath(p)) != workdir] + [workdir]
    # Readable outside the working directory: the interpreter's own library, and this file (for tracebacks).
    roots = [p for p in sys.path if p and os.path.exists(p)] + [SELF]
    with open(os.path.join(workdir, "main.py"), encoding="utf-8") as f:
        code = compile(f.read(), "main.py", "exec")
    _install(workdir, roots, spec.get("allow_net", []), report_fd)
    del spec, roots, report_fd
    module = types.ModuleType("__main__")
    module.__file__ = "main.py"
    modules, out, err, run = sys.modules, sys.stdout, sys.stderr, _execute
    modules["__main__"] = module
    # Nothing in this module may be reachable from the agent's frames: f_back raises no audit event. The hook holds
    # its own copies of everything it uses, so this file's globals (Policy, the rule factory, the tables) go.
    globals().clear()
    try:
        run(code, module.__dict__)
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - reported without walking frames, which the policy refuses
        tb, line = exc.__traceback__, None
        while tb is not None:
            line, tb = tb.tb_lineno, tb.tb_next
        out.flush()
        err.write("main.py, last line run: %s%s%s: %s%s" % (line, chr(10), type(exc).__name__, exc, chr(10)))
        return 1
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

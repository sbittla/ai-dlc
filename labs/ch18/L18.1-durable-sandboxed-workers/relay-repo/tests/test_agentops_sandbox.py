"""The sandbox for agent-written code (4.30.0, ADR-050): what it refuses, what it allows, and its limits.

Each escape attempt below is inert: it tries to read, connect or start something, and the test checks that
the attempt was refused before it happened. The local listener stands in for an internal service."""

import os
import socket
import threading

import pytest

from relay.agentops.sandbox import SandboxPolicy, child_env, run_code
from relay.agentops.sandbox_child import decide, make_policy

FAST = SandboxPolicy(timeout_s=5)

ESCAPES = {
    "read a file outside the working directory": ("print(open('../private/stdout').read())", "refused:open:read"),
    "write outside the working directory": ("open('../planted.txt', 'w').write('x')", "refused:open:write"),
    "open Relay's database": ("import sqlite3\nsqlite3.connect('../relay.db')", "refused:import:sqlite3"),
    "list the parent directory": ("import os\nprint(os.listdir('..'))", "refused:os.listdir"),
    "reach the metadata endpoint": ("import socket\nsocket.create_connection(('169.254.169.254', 80), 1)",
                                    "refused:network"),
    "resolve an outside name": ("import socket\nsocket.getaddrinfo('exfil.example.net', 443)", "refused:network"),
    "run a shell command": ("import os\nos.system('echo hi')", "refused:process"),
    "start a process": ("import subprocess\nsubprocess.run(['echo', 'hi'])", "refused:"),
    "load native code": ("import ctypes", "refused:import:ctypes"),
    "reopen an inherited descriptor": ("print(open(3).read())", "refused:open:descriptor"),
    "link to a file outside": ("import os\nos.symlink('../relay.db', 'db')", "refused:os.symlink"),
}


@pytest.mark.parametrize("name", sorted(ESCAPES))
def test_each_escape_attempt_is_refused_and_recorded(name):
    code, reason = ESCAPES[name]
    result = run_code(code, policy=FAST)
    assert result.status == "error" and result.refused
    assert result.refusals[0]["reason"].startswith(reason), result.refusals
    assert "PermissionError: sandbox refused" in result.stderr


def test_a_refusal_the_code_catches_is_still_recorded():
    code = "try:\n    open('../x').read()\nexcept PermissionError:\n    print('carried on')\n"
    result = run_code(code, policy=FAST)
    assert result.status == "ok" and result.stdout.strip() == "carried on"
    assert [r["reason"] for r in result.refusals] == ["refused:open:read"]


def test_ordinary_test_code_runs_with_its_files_and_the_standard_library():
    code = ("import json, math, re, unittest\nfrom feature import add\nassert add(2, 3) == 5\n"
            "open('report.json', 'w').write(json.dumps({'sqrt': math.sqrt(16)}))\n"
            "print(open('report.json').read())\n")
    result = run_code(code, {"feature.py": "def add(a, b):\n    return a + b\n"}, FAST)
    assert (result.status, result.refusals, result.stdout.strip()) == ("ok", (), '{"sqrt": 4.0}')


def test_the_worker_environment_does_not_reach_the_code(monkeypatch):
    monkeypatch.setenv("RELAY_PAYMENTS_KEY", "rk_test_not_a_real_key")
    result = run_code("import os\nprint(os.environ.get('RELAY_PAYMENTS_KEY'))", policy=FAST)
    assert result.stdout.strip() == "None"
    assert set(child_env()) <= {"SYSTEMROOT"}


def test_the_pilot_way_of_running_code_leaks_the_environment(monkeypatch):
    monkeypatch.setenv("RELAY_PAYMENTS_KEY", "rk_test_not_a_real_key")
    result = run_code("import os\nprint(os.environ.get('RELAY_PAYMENTS_KEY'))", unrestricted=True, policy=FAST)
    assert result.stdout.strip() == "rk_test_not_a_real_key"


def test_a_loop_that_never_ends_is_killed_at_the_timeout():
    result = run_code("while True:\n    pass\n", policy=SandboxPolicy(timeout_s=1))
    assert result.status == "timeout" and result.exit_code is None


def test_output_past_the_cap_is_cut_and_flagged():
    result = run_code("print('x' * 200000)", policy=SandboxPolicy(timeout_s=5, max_output_bytes=1000))
    assert result.status == "output_limit" and len(result.stdout) == 1000


def _listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def serve():
        try:
            while True:
                srv.accept()[0].close()
        except OSError:  # the test closed the listener
            pass
    threading.Thread(target=serve, daemon=True).start()
    return srv, srv.getsockname()[1]


def test_an_allowlisted_host_and_port_is_reachable_and_nothing_else_is():
    srv, port = _listener()
    try:
        allowed = SandboxPolicy(timeout_s=5, allow_net=(("127.0.0.1", port),))
        ok = run_code(f"import socket\nsocket.create_connection(('127.0.0.1', {port}), 2).close()\nprint('ok')",
                      policy=allowed)
        other = run_code(f"import socket\nsocket.create_connection(('127.0.0.1', {port + 1}), 2)", policy=allowed)
        none = run_code(f"import socket\nsocket.create_connection(('127.0.0.1', {port}), 2)", policy=FAST)
    finally:
        srv.close()
    assert ok.status == "ok" and ok.stdout.strip() == "ok"
    assert other.refusals[0]["reason"] == "refused:network"
    assert none.refusals[0]["reason"] == "refused:network"


def test_an_allowlist_entry_must_be_exact():
    with pytest.raises(ValueError):
        SandboxPolicy(allow_net=(("*.relay.example", 443),))
    with pytest.raises(ValueError):
        SandboxPolicy(allow_net=(("proxy", 0),))


def test_decide_is_a_pure_policy():
    policy = make_policy("work", ["lib"], [])
    assert decide("open", (os.path.join("work", "a.txt"), "w", 0), policy) is None
    assert decide("open", (os.path.join("lib", "os.py"), "r", 0), policy) is None
    assert decide("open", (os.path.join("lib", "os.py"), "w", 0), policy) == "refused:open:write"
    assert decide("open", ("elsewhere.txt", "r", 0), policy) == "refused:open:read"
    assert decide("import", ("json", None), policy) is None
    assert decide("import", ("ctypes.util", None), policy) == "refused:import:ctypes"
    assert decide("import", ("alias._ctypes", os.path.join("lib", "_ctypes.pyd")), policy) == "refused:import:_ctypes"
    shadow = os.path.join("lib", "_ctypes.cpython-311.so")
    assert decide("import", ("innocent", shadow), policy) == "refused:import:native"
    assert decide("import", ("mine", os.path.join("work", "mine.so")), policy) == "refused:import:native"
    assert decide("socket.bind", (None, ("0.0.0.0", 80)), policy) == "refused:network"
    assert decide("os.posix_spawn", ("/bin/sh",), policy) == "refused:process"
    assert decide("winreg.OpenKey", (), policy) == "refused:native"
    assert decide("_winapi.CreateFile", ("x",), policy) == "refused:native"
    assert decide("gc.get_objects", (), policy) == "refused:introspection"
    assert decide("object.__getattr__", (None, "tb_frame"), policy) == "refused:introspection"
    assert decide("object.__getattr__", (None, "__code__"), policy) is None
    assert decide("os.truncate", (3, 0), policy) == "refused:os.truncate:descriptor"
    assert decide("compile", (b"", "x"), policy) is None
    assert isinstance(policy.allow_net, frozenset) and isinstance(policy.read_roots, tuple)


# Round-1 review probes: each reached state or files the policy meant to keep out of reach. Each must now fail.
PROBES = {
    "collector search for the policy": (
        "import gc\nprint([o for o in gc.get_objects() if isinstance(o, dict) and 'allow_net' in o])",
        "refused:introspection"),
    "traceback frame of the hook": (
        "try:\n    open('../x')\nexcept PermissionError as e:\n    print(e.__traceback__.tb_frame.f_locals)",
        "refused:introspection"),
    "ctypes core under another name": (
        "import importlib.util, os, sys\n"
        "p = [os.path.join(d, f) for d in sys.path if os.path.isdir(d) for f in os.listdir(d)\n"
        "     if f.split('.')[0] == '_ctypes' and f.endswith(('.pyd', '.so'))][0]\n"
        "spec = importlib.util.spec_from_file_location('alias._ctypes', p)\n"
        "spec.loader.exec_module(importlib.util.module_from_spec(spec))", "refused:import:_ctypes"),
    "sqlite ATTACH from memory": (
        "import sqlite3\nc = sqlite3.connect(':memory:')\nc.execute(\"ATTACH DATABASE '../relay.db' AS x\")",
        "refused:import:sqlite3"),
    "truncate the report channel": ("import os\nos.ftruncate(3, 0)", "refused:os.truncate:descriptor"),
    "trace function to see frames": ("import sys\nsys.settrace(lambda *a: None)", "refused:introspection"),
}


@pytest.mark.parametrize("name", sorted(PROBES))
def test_round_one_probes_are_refused(name):
    code, reason = PROBES[name]
    result = run_code(code, policy=FAST)
    assert result.refused and [r["reason"] for r in result.refusals][-1] == reason, result.refusals
    assert result.status == "error"


def test_the_frame_chain_holds_no_policy_or_hook():
    code = ("import sys\nfound = []\nfor depth in range(1, 6):\n    try:\n        f = sys._getframe(depth)\n"
            "    except ValueError:\n        break\n"
            "    found += [k for k, v in f.f_locals.items() if k in ('policy', 'hook', 'report_fd')\n"
            "              or getattr(v, '__name__', '') == 'hook']\nprint(found)")
    result = run_code(code, policy=FAST)
    assert (result.status, result.stdout.strip(), result.refusals) == ("ok", "[]", ())


def test_closing_the_report_channel_ends_the_run_and_is_recorded():
    code = ("import os\nfor fd in range(3, 8):\n    try:\n        os.close(fd)\n    except OSError:\n"
            "        pass\ntry:\n    open('../x')\nexcept PermissionError:\n    print('hidden?')")
    result = run_code(code, policy=FAST)
    assert result.exit_code == 86 and result.refusals[-1]["reason"] == "refused:report-channel"
    assert "hidden?" not in result.stdout


def test_forged_report_lines_only_add_refusals():
    result = run_code("import os\nos.write(3, b'not json\\n')\nprint('done')", policy=FAST)
    assert result.status == "ok" and [r["reason"] for r in result.refusals] == ["refused:unparsable-report"]


def test_what_the_local_layer_does_not_stop():
    """Metadata of files outside: os.stat raises no audit event. A known limit (ADR-050)."""
    result = run_code("import os\nprint(os.path.exists('..'))", policy=FAST)
    assert (result.status, result.stdout.strip(), result.refusals) == ("ok", "True", ())


@pytest.mark.skipif(os.name != "nt", reason="the Windows file API exists only on Windows")
def test_windows_file_api_is_refused():
    result = run_code("import _winapi\n_winapi.CreateFile('../x', 0x80000000, 1, 0, 3, 0, 0)", policy=FAST)
    assert result.refusals[-1]["reason"] == "refused:native"


@pytest.mark.skipif(os.name != "posix", reason="resource limits need POSIX; on Windows only the timeout applies")
def test_memory_is_capped_on_posix():
    result = run_code("x = bytearray(512 * 1024 * 1024)\nprint('allocated')",
                      policy=SandboxPolicy(timeout_s=10, memory_bytes=256 * 1024 * 1024))
    assert result.status == "error" and "MemoryError" in result.stderr

"""A pytest plugin that records why each test passed or failed, for the grader (testfirst.grade).

Loaded with `-p testfirst.plugin`; writes one JSON line per test to the file
named by the TESTFIRST_RESULTS environment variable. For a failure it records
the exception type, and whether the innermost frame of the traceback is inside
`src/relay/`: a NotImplementedError raised there means the test reached code
that does not exist yet, which is the right reason for a test-first test to fail.

With TESTFIRST_COVER (comma-separated path suffixes) it also records which
lines of those files ran, for the incident report's line coverage.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_COVERED: dict[str, set[int]] = {}


def pytest_configure(config):
    """With TESTFIRST_COVER set, record the lines executed in files whose path ends with one of its suffixes."""
    suffixes = tuple(s for s in os.environ.get("TESTFIRST_COVER", "").split(",") if s)
    if not suffixes:
        return

    def tracer(frame, event, arg):
        name = frame.f_code.co_filename.replace("\\", "/")
        if not name.endswith(suffixes):
            return None
        key = next(s for s in suffixes if name.endswith(s))
        lines = _COVERED.setdefault(key, set())

        def local(f, e, a):
            if e == "line":
                lines.add(f.f_lineno)
            return local
        if event == "call":
            lines.add(frame.f_lineno)
        return local

    sys.settrace(tracer)


def pytest_unconfigure(config):
    out = os.environ.get("TESTFIRST_COVER_OUT")
    if out and os.environ.get("TESTFIRST_COVER"):
        sys.settrace(None)
        Path(out).write_text(json.dumps({k: sorted(v) for k, v in _COVERED.items()}, sort_keys=True),
                             encoding="utf-8")


def pytest_runtest_logreport(report):
    if report.when != "call" and not (report.when == "setup" and report.failed):
        return
    record = {"test": report.nodeid.split("::", 1)[-1], "file": Path(report.nodeid.split("::", 1)[0]).name,
              "outcome": report.outcome, "exception": None, "in_src": False}
    if report.failed and report.longrepr is not None and hasattr(report.longrepr, "reprcrash"):
        crash = report.longrepr.reprcrash
        record["exception"] = crash.message.split(":", 1)[0].strip()
        frames = getattr(getattr(report.longrepr, "reprtraceback", None), "reprentries", [])
        last = frames[-1] if frames else None
        location = getattr(getattr(last, "reprfileloc", None), "path", "") or crash.path
        record["in_src"] = "src/relay/" in str(location).replace("\\", "/")
    path = os.environ.get("TESTFIRST_RESULTS")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

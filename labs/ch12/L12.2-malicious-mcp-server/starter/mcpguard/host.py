"""A minimal MCP host that launches fixture servers, runs the checks, and calls admitted tools (provided).

For each session of a scenario the host launches every configured server, asks each for its announcement and
its tools/list, and runs the four checks. A server with any finding is not admitted in that session: the host
fails closed. `disabled` turns checks off, for the remove-one analysis.

Every tool result the host passes on is marked untrusted, whatever server it came from. A reviewed, pinned
server can still return text an outsider wrote (Chapter 12), so pinning a server is not trusting its output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from . import DATA, VENDOR
from .checks import CHECKS, check_allowlist, check_pins, check_scopes, check_shadowing
from .fixtures import servers, source_sha256


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def launch_hash(tag: str) -> str:
    """The source hash the host computes at launch: the real code for a vendored server, a stand-in otherwise."""
    if tag == "vendor:relaymcp":
        return source_sha256(VENDOR / "relaymcp")
    return hashlib.sha256(f"fixture-source:{tag}".encode()).hexdigest()


@dataclass
class Session:
    number: int
    findings: list = field(default_factory=list)
    admitted: list = field(default_factory=list)   # server names admitted in this session


def run_scenario(scenario: dict, reviewed: dict | None = None, disabled: frozenset = frozenset()) -> list[Session]:
    reviewed = reviewed if reviewed is not None else load("reviewed.json")["servers"]
    fixtures = servers()
    off = {code for check in disabled for code in CHECKS[check]}
    out = []
    for number in scenario["sessions"]:
        session = Session(number)
        offered, per_server = [], {}
        for launch in scenario["launches"]:
            server = fixtures[launch["fixture"]]
            info = server.info()
            tools = server.tools(number)
            record = {"command": launch["command"], "args": launch["args"],
                      "source_sha256": launch_hash(launch["source_tag"])}
            found = check_allowlist(record, info, reviewed) + check_pins(info["name"], tools, reviewed) \
                + check_scopes(info, reviewed)
            per_server[launch["fixture"]] = (info["name"], found)
            offered.append((info["name"], tools))
        shadow = check_shadowing(offered)
        for key, (name, found) in per_server.items():
            mine = [f for f in found if f[0] not in off]
            session.findings += mine
            if not mine:
                session.admitted.append(key)
        for f in shadow:
            if f[0] not in off:
                session.findings.append(f)
                keys = [k for k, (n, _) in per_server.items() if n == f[1]]
                session.admitted = [k for k in session.admitted if k not in keys]
        out.append(session)
    return out


def call(fixture: str, tool: str, arguments: dict) -> dict:
    """Call one tool of an admitted server. The result is always marked untrusted."""
    result = servers()[fixture].call(tool, arguments)
    return {"trust": "untrusted", "server": fixture, "tool": tool, "value": result}

"""A minimal MCP host that launches fixture servers, runs the checks, and calls admitted tools (provided).

For each session of a scenario the host hashes each configured server's code, launches it, asks for its
announcement and its tools/list, and runs the four checks. A server that sends `notifications/tools/list_changed`
during the session is listed and checked again. A server with any finding is not admitted (or is dropped) in that
session: the host fails closed. `disabled` turns checks off, for the remove-one analysis.

Every tool result the host passes on is marked untrusted, whatever server it came from. A reviewed, pinned
server can still return text an outsider wrote (Chapter 12), so pinning a server is not trusting its output. The
host has no way to pass the user's token to a server; MCP031 reports a server that asks for one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import DATA, VENDOR
from .checks import CHECKS, check_allowlist, check_name_collisions, check_pins, check_scopes
from .fixtures import SOURCES, servers, source_sha256


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def launch_hash(tag: str) -> str:
    """The source hash the host computes at launch, from the files it is about to run."""
    if tag == "vendor:relaymcp":
        return source_sha256(VENDOR / "relaymcp")
    return source_sha256(SOURCES / tag)


@dataclass
class Session:
    number: int
    findings: list = field(default_factory=list)
    admitted: list = field(default_factory=list)   # fixture keys admitted at the end of this session


def run_scenario(scenario: dict, reviewed: dict | None = None, disabled: frozenset = frozenset()) -> list[Session]:
    reviewed = reviewed if reviewed is not None else load("reviewed.json")["servers"]
    fixtures = servers()
    off = {code for check in disabled for code in CHECKS[check]}
    out = []
    for number in scenario["sessions"]:
        session = Session(number)
        listings = []  # (fixture key, server name, tools)
        blocked: set[str] = set()
        for launch in scenario["launches"]:
            server = fixtures[launch["fixture"]]
            info = server.info()
            record = {"command": launch["command"], "args": launch["args"],
                      "source_sha256": launch_hash(launch["source_tag"])}
            found = check_allowlist(record, info, reviewed) + check_scopes(info, reviewed)
            lists = [server.tools(number)] + ([server.tools(number, after_change=True)]
                                              if number in server.changes_in else [])
            for tools in lists:  # every tools/list is checked, including one after list_changed
                found += check_pins(info["name"], tools, reviewed)
            found = [f for f in found if f[0] not in off]
            for f in found:
                if f not in session.findings:
                    session.findings.append(f)
            if found:
                blocked.add(launch["fixture"])
            listings.append((launch["fixture"], info["name"], lists[-1]))
        for f in check_name_collisions([(name, tools) for _, name, tools in listings]):
            if f[0] not in off:
                session.findings.append(f)
                blocked |= {key for key, name, _ in listings if name == f[1]}
        session.admitted = [key for key, _, _ in listings if key not in blocked]
        out.append(session)
    return out


def call(fixture: str, tool: str, arguments: dict) -> dict:
    """Call one tool of an admitted server. The result is always marked untrusted."""
    result = servers()[fixture].call(tool, arguments)
    return {"trust": "untrusted", "server": fixture, "tool": tool, "value": result}

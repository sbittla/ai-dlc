"""The host's checks on MCP servers (TODOs 1 to 5 in starter/).

None of these reads a description for meaning. They compare what a server presents with what a person reviewed:
which server it is and how it was launched, the exact definition of every tool, the names it claims, and the
scopes and audience it asks for. A finding is a (code, server, detail) tuple.

    MCP001  server not in the reviewed record                       (allowlist)
    MCP002  launch command or arguments differ from the review       (allowlist)
    MCP003  source hash at launch differs from the review            (allowlist)
    MCP004  announced version differs from the review                (allowlist)
    MCP010  a tool's definition hash differs from the review         (pin)
    MCP011  a tool that was not reviewed                             (pin)
    MCP020  a tool name offered by more than one server              (shadowing)
    MCP030  a scope the review did not grant                         (scope)
    MCP031  the server asks for the user's token to be passed through (scope)
    MCP032  the token audience is not the server itself              (scope)
"""

from __future__ import annotations

import hashlib
import json

Finding = tuple[str, str, str]


def definition_hash(tool: dict) -> str:
    """TODO 1. SHA-256 (hex) of the tool's name, description and inputSchema as canonical JSON:
    keys sorted, separators (",", ":"), ensure_ascii=False, UTF-8. Other keys are ignored."""
    body = {"name": tool["name"], "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema", {})}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def check_allowlist(launch: dict, info: dict, reviewed: dict) -> list[Finding]:
    """TODO 2. MCP001 to MCP004 for one launched server, in code order.

    `launch` is {"command", "args", "source_sha256"} as the host launched it; `info` is the server's own
    announcement; `reviewed` is the reviewed record's `servers` map. An unlisted server gets MCP001 only.
    """
    name = info["name"]
    record = reviewed.get(name)
    if record is None:
        return [("MCP001", name, "not in the reviewed record")]
    out: list[Finding] = []
    if launch["command"] != record["command"] or launch["args"] != record["args"]:
        out.append(("MCP002", name, "launch differs from the review"))
    if launch["source_sha256"] != record["source_sha256"]:
        out.append(("MCP003", name, "source hash differs from the review"))
    if info["version"] != record["version"]:
        out.append(("MCP004", name, f"version {info['version']}, reviewed {record['version']}"))
    return out


def check_pins(name: str, tools: list[dict], reviewed: dict) -> list[Finding]:
    """TODO 3. MCP010 and MCP011 for one server's tools/list, in tool order. Nothing for an unlisted server
    (the allowlist reports it)."""
    record = reviewed.get(name)
    if record is None:
        return []
    out: list[Finding] = []
    for tool in tools:
        pinned = record["tools"].get(tool["name"])
        if pinned is None:
            out.append(("MCP011", name, f"{tool['name']} was not reviewed"))
        elif definition_hash(tool) != pinned:
            out.append(("MCP010", name, f"{tool['name']} changed since review"))
    return out


def check_shadowing(offered: list[tuple[str, list[dict]]]) -> list[Finding]:
    """TODO 4. MCP020 for every server, after the first, that offers a tool name an earlier server offered.
    `offered` is [(server name, tools)] in launch order."""
    seen: dict[str, str] = {}
    out: list[Finding] = []
    for name, tools in offered:
        for tool in tools:
            first = seen.get(tool["name"])
            if first is not None and first != name:
                out.append(("MCP020", name, f"{tool['name']} is already offered by {first}"))
            else:
                seen.setdefault(tool["name"], name)
    return out


def check_scopes(info: dict, reviewed: dict) -> list[Finding]:
    """TODO 5. MCP030 (one per extra scope, sorted), MCP031, MCP032, in that order. Nothing for an unlisted
    server."""
    record = reviewed.get(info["name"])
    if record is None:
        return []
    out: list[Finding] = [("MCP030", info["name"], f"scope {s} not granted")
                          for s in sorted(set(info["scopes"]) - set(record["scopes"]))]
    if info["token_passthrough"]:
        out.append(("MCP031", info["name"], "asks for the user's token to be passed through"))
    if info["audience"] != info["name"]:
        out.append(("MCP032", info["name"], f"audience {info['audience']}"))
    return out


CHECKS = {"allowlist": ("MCP001", "MCP002", "MCP003", "MCP004"), "pin": ("MCP010", "MCP011"),
          "shadowing": ("MCP020",), "scope": ("MCP030", "MCP031", "MCP032")}

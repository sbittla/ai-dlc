"""The host's checks on MCP servers (TODOs 1 to 5 in starter/).

None of these reads a description for meaning. They compare what a server presents with what a person reviewed:
which server it is and the code the host launched, the exact definition of every tool, the names it claims, and
the scopes and token audience it asks for. A finding is a (code, server, detail) tuple.

    MCP001  server not in the reviewed record                          (allowlist)
    MCP002  launch command or arguments differ from the review          (allowlist)
    MCP003  source hash at launch differs from the review               (allowlist)
    MCP004  announced version differs from the review                   (allowlist)
    MCP010  a tool's definition hash differs from the review            (pin)
    MCP011  a tool that was not reviewed                                (pin)
    MCP020  a tool name offered by more than one server                 (name collision)
    MCP030  a scope the review did not grant                            (scope)
    MCP031  the server asks for the user's token to be passed through   (scope)
    MCP032  the token audience is not the one the review recorded       (scope)

What they cannot catch: a poisoned description that a reviewer approved. A pin freezes what was reviewed,
including what the reviewer missed. Only reading the description at review catches that.
"""

from __future__ import annotations

import hashlib
import json

Finding = tuple[str, str, str]


def definition_hash(tool: dict) -> str:
    """TODO 1. SHA-256 (hex) of the WHOLE tool object as canonical JSON: keys sorted at every level, separators
    (",", ":"), ensure_ascii=False, UTF-8. Every field counts (name, title, description, inputSchema,
    outputSchema, annotations), so a change to any of them is a change."""
    raise NotImplementedError("TODO 1")


def check_allowlist(launch: dict, info: dict, reviewed: dict) -> list[Finding]:
    """TODO 2. MCP001 to MCP004 for one launched server, in code order.

    `launch` is {"command", "args", "source_sha256"} as the host launched it (the hash is computed by the host
    from the files it is about to run); `info` is the server's own announcement; `reviewed` is the reviewed
    record's `servers` map. An unlisted server gets MCP001 only.
    """
    raise NotImplementedError("TODO 2")


def check_pins(name: str, tools: list[dict], reviewed: dict) -> list[Finding]:
    """TODO 3. MCP010 and MCP011 for one server's tools/list, in tool order. Nothing for an unlisted server
    (the allowlist reports it)."""
    raise NotImplementedError("TODO 3")


def check_name_collisions(offered: list[tuple[str, list[dict]]]) -> list[Finding]:
    """TODO 4. MCP020 for every server, after the first, that offers a tool name an earlier server offered.
    `offered` is [(server name, tools)] in launch order."""
    raise NotImplementedError("TODO 4")


def check_scopes(info: dict, reviewed: dict) -> list[Finding]:
    """TODO 5. MCP030 (one per extra scope, sorted), MCP031, MCP032, in that order. The audience is compared
    with the REVIEWED record's audience, never with anything the server announces about itself. Nothing for an
    unlisted server. (The host has no passthrough path at all; MCP031 reports a server that asks for one.)"""
    raise NotImplementedError("TODO 5")


CHECKS = {"allowlist": ("MCP001", "MCP002", "MCP003", "MCP004"), "pin": ("MCP010", "MCP011"),
          "name-collision": ("MCP020",), "scope": ("MCP030", "MCP031", "MCP032")}

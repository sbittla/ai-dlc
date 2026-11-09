"""TODOs 1 to 5 on small hand-made records. Expected values are worked out by hand from the docstrings."""

import hashlib
import json

from mcpguard.checks import check_allowlist, check_pins, check_scopes, check_shadowing, definition_hash

TOOL = {"name": "save_note", "description": "Save a note.", "inputSchema": {"type": "object"}, "annotations": {}}
EXPECTED_HASH = hashlib.sha256(
    b'{"description":"Save a note.","inputSchema":{"type":"object"},"name":"save_note"}').hexdigest()
REVIEWED = {"notes": {"command": "python", "args": ["-m", "notes"], "source_sha256": "aa", "version": "1.0.0",
                      "scopes": ["notes:write"], "audience": "notes", "tools": {"save_note": EXPECTED_HASH}}}
INFO = {"name": "notes", "version": "1.0.0", "scopes": ["notes:write"], "audience": "notes",
        "token_passthrough": False}
LAUNCH = {"command": "python", "args": ["-m", "notes"], "source_sha256": "aa"}


def test_todo1_definition_hash_is_canonical_and_ignores_other_keys():
    assert definition_hash(TOOL) == EXPECTED_HASH
    reordered = json.loads(json.dumps({"inputSchema": {"type": "object"}, "name": "save_note",
                                       "description": "Save a note."}))
    assert definition_hash(reordered) == EXPECTED_HASH
    assert definition_hash({**TOOL, "description": "Save a note. "}) != EXPECTED_HASH  # one space is a change


def test_todo2_allowlist_in_code_order_and_unlisted_alone():
    assert check_allowlist(LAUNCH, INFO, REVIEWED) == []
    changed = {"command": "python", "args": ["-m", "notes", "--x"], "source_sha256": "bb"}
    assert [f[0] for f in check_allowlist(changed, {**INFO, "version": "1.1.0"}, REVIEWED)] == [
        "MCP002", "MCP003", "MCP004"]
    assert check_allowlist(changed, {**INFO, "name": "other"}, REVIEWED) == [
        ("MCP001", "other", "not in the reviewed record")]


def test_todo3_pins_report_changed_and_unreviewed_tools_and_ignore_unlisted_servers():
    assert check_pins("notes", [TOOL], REVIEWED) == []
    changed = {**TOOL, "description": "Save a note. [[INJECTION technique=tool-poisoning]]"}
    extra = {"name": "send", "description": "Send.", "inputSchema": {}}
    assert check_pins("notes", [changed, extra], REVIEWED) == [
        ("MCP010", "notes", "save_note changed since review"), ("MCP011", "notes", "send was not reviewed")]
    assert check_pins("other", [changed], REVIEWED) == []


def test_todo4_shadowing_flags_every_later_server_that_reuses_a_name():
    a = ("a", [{"name": "query"}, {"name": "list"}])
    b = ("b", [{"name": "query"}])
    c = ("c", [{"name": "list"}, {"name": "query"}])
    assert check_shadowing([a, b, c]) == [("MCP020", "b", "query is already offered by a"),
                                          ("MCP020", "c", "list is already offered by a"),
                                          ("MCP020", "c", "query is already offered by a")]
    assert check_shadowing([a]) == []


def test_todo5_scopes_extra_sorted_then_passthrough_then_audience():
    assert check_scopes(INFO, REVIEWED) == []
    bad = {**INFO, "scopes": ["notes:write", "z:all", "a:read"], "token_passthrough": True, "audience": "relay-api"}
    assert check_scopes(bad, REVIEWED) == [
        ("MCP030", "notes", "scope a:read not granted"), ("MCP030", "notes", "scope z:all not granted"),
        ("MCP031", "notes", "asks for the user's token to be passed through"),
        ("MCP032", "notes", "audience relay-api")]
    assert check_scopes({**bad, "name": "other"}, REVIEWED) == []

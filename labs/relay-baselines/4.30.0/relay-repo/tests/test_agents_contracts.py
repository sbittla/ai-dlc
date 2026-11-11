"""Typed tool contracts and argument validation (4.24.0, ADR-025)."""

import pytest

from relay.agents import HELPER_TOOLS, Param, ToolContract, idempotency_key, path_problem, validate_args

EDIT = HELPER_TOOLS["edit_file"]
WRITE = frozenset({"src/relay/x.py"})


def test_the_helper_has_exactly_seven_tools_and_one_external_effect():
    assert sorted(HELPER_TOOLS) == ["edit_file", "open_pull_request", "read_file", "read_task", "run_prcheck",
                                    "run_tests", "search_code"]
    external = [c.name for c in HELPER_TOOLS.values() if c.effect == "external"]
    assert external == ["open_pull_request"]
    assert HELPER_TOOLS["open_pull_request"].approval == "requester"


def test_no_helper_tool_runs_a_shell_or_merges():
    names = " ".join(HELPER_TOOLS)
    assert not any(word in names for word in ("shell", "exec", "merge", "approve", "push_main"))


@pytest.mark.parametrize("args, problems", [
    ({"path": "src/relay/x.py", "content": "y"}, []),
    ({"path": "src/relay/x.py"}, ["content: missing"]),
    ({"path": "src/relay/x.py", "content": 3}, ["content: expected text"]),
    ({"path": "src/relay/x.py", "content": "y", "force": True}, ["unknown argument 'force'"]),
    ({"path": "src/relay/y.py", "content": "y"}, ["path: not in the task's file list"]),
    ({"path": "tests/test_x.py", "content": "y"},
     ["path: path must not be a test file; approved tests are not the agent's"]),
    ({"path": "../secrets.txt", "content": "y"}, ["path: path must not contain empty, '.' or '..' parts"]),
    ({"path": "/etc/passwd", "content": "y"}, ["path: path must be relative, with forward slashes"]),
])
def test_edit_file_arguments(args, problems):
    assert validate_args(EDIT, args, WRITE) == problems


def test_reads_may_not_touch_secrets_or_the_agent_governance_files():
    read = HELPER_TOOLS["read_file"]
    assert validate_args(read, {"path": "src/relay/store.py"}) == []
    for path in (".env", "deploy/key.pem", "governance/agents.json", "infra/agents.tf", "infra/detection/rules.json"):
        assert path_problem(path) == "path is never readable by an agent"
        assert validate_args(read, {"path": path}) == ["path: path is never readable by an agent"]


def test_types_are_strict_and_enums_are_closed():
    run = HELPER_TOOLS["run_tests"]
    assert validate_args(run, {"target": "suite"}) == []
    assert validate_args(run, {"target": "everything"}) == ["target: not one of approved, suite"]
    count = ToolContract("t", "d", (Param("n", "int"),), "read")
    assert validate_args(count, {"n": True}) == ["n: expected int"]  # a bool is not an int here


def test_lengths_are_bounded():
    search = HELPER_TOOLS["search_code"]
    assert validate_args(search, {"pattern": "x" * 121}) == ["pattern: longer than 120"]


def test_an_external_effect_needs_approval_or_an_idempotent_handler():
    with pytest.raises(ValueError):
        ToolContract("post", "d", (), "external")
    ToolContract("post", "d", (), "external", idempotent=True)


def test_the_schema_shown_to_the_model_forbids_extra_arguments():
    schema = HELPER_TOOLS["open_pull_request"].schema()
    assert schema["input_schema"]["additionalProperties"] is False
    assert schema["input_schema"]["required"] == ["branch", "title", "body"]  # the diff's hash is derived
    assert HELPER_TOOLS["open_pull_request"].derived == ("diff_sha256",)
    assert HELPER_TOOLS["edit_file"].derived == ("before_sha256",)


def test_idempotency_keys_cover_the_named_fields_only_and_reads_have_none():
    pr = HELPER_TOOLS["open_pull_request"]
    a = {"branch": "agent/T-1", "title": "one", "body": "x", "diff_sha256": "1"}
    b = {"branch": "agent/T-1", "title": "two", "body": "y", "diff_sha256": "2"}
    assert idempotency_key("run-1", pr, a) == idempotency_key("run-1", pr, b)  # one pull request per branch
    assert idempotency_key("run-2", pr, a) != idempotency_key("run-1", pr, a)
    assert idempotency_key("run-1", HELPER_TOOLS["read_file"], {"path": "a"}) is None
    e1 = idempotency_key("run-1", EDIT, {"path": "src/relay/x.py", "content": "1", "before_sha256": "s"})
    e2 = idempotency_key("run-1", EDIT, {"path": "src/relay/x.py", "content": "2", "before_sha256": "s"})
    e3 = idempotency_key("run-1", EDIT, {"path": "src/relay/x.py", "content": "1", "before_sha256": "t"})
    assert len({e1, e2, e3}) == 3  # the same content from a different starting state is a different edit

"""TODO 3: run_workflow, on one small task with the simulator's draws forced, so every step and cost is by hand.

The task has one listed file of 1,000 tokens and an approved test file of 1,800. With skill and p_attempt at 1
the first attempt is correct. The implement call sends 1,200 + 600 + 1,000 + 1,800 = 4,600 tokens and writes
900: $0.0184 + $0.018 = $0.0364. The describe call sends 1,200 + 600 + 900 + 200 = 2,900 and writes 400:
$0.0116 + $0.008 = $0.0196. Total $0.056.
"""

import copy

import pytest

from agentlab.designs import run_workflow
from agentlab.evaluate import config
from agentlab.runtime import Runtime
from agentlab.world import Task
from relay.agents import Budget


def task(shape="local", by_import=False):
    return Task(task_id="HT-900", family="F99", split="dev", shape=shape, difficulty="easy", title="Fixture",
                files=("src/relay/roles.py",), tests="tests/test_f99.py", test_count=3, symbol="sym_f99",
                context_file="src/relay/api.py" if shape == "cross_file" else None, context_by_import=by_import,
                outside_file="src/relay/api.py" if shape == "out_of_scope" else None,
                tokens={"src/relay/roles.py": 1000, "tests/test_f99.py": 1800, "src/relay/api.py": 500})


def runtime(t, **behaviour):
    cfg, designs, registry = config()
    cfg = copy.deepcopy(cfg)
    cfg["behaviour"].update({"skill": {"easy": 1.0, "hard": 1.0}, "p_attempt": 1.0, "p_hack": 0.0,
                             "p_notice_seen": 0.0, "p_notice_unseen": 0.0, **behaviour})
    return Runtime(t, 1, "workflow", cfg, Budget(max_steps=30, max_usd=0.30, max_seconds=240), registry)


def tools(rt):
    return [s["tool"] for s in rt.store.steps(rt.run_id)]


def test_a_local_task_in_one_attempt():
    rt = runtime(task())
    assert run_workflow(rt, {"max_attempts": 3}) == ("finished", "pull request opened")
    assert tools(rt) == ["read_task", "read_file", "read_file", "edit_file", "run_tests", "run_tests", "run_prcheck",
                         "open_pull_request"]
    assert rt.meter.model_calls == 2 and rt.meter.usd == pytest.approx(0.056)
    assert len(rt.github.pulls) == 1 and rt.approvals == 1 and rt.sandbox.variant() == "correct"


def test_an_imported_context_file_is_read_and_used():
    rt = runtime(task("cross_file", by_import=True))
    run_workflow(rt, {"max_attempts": 3})
    assert tools(rt)[:4] == ["read_task", "read_file", "read_file", "read_file"]
    assert rt.sandbox.variant() == "correct"


def test_three_failed_attempts_hand_back():
    rt = runtime(task(), p_attempt=0.0)
    status, reason = run_workflow(rt, {"max_attempts": 3})
    assert (status, reason) == ("handed_back", "repeated_failure:tests:tests/test_f99.py")
    assert tools(rt).count("run_tests") == 3 and rt.meter.model_calls == 3 and rt.github.pulls == []


def test_a_noticed_out_of_scope_task_is_handed_back_before_any_edit():
    rt = runtime(task("out_of_scope", by_import=True), p_notice_seen=1.0)
    assert run_workflow(rt, {"max_attempts": 3}) == ("handed_back", "needs a file outside the task's list")
    assert "edit_file" not in tools(rt)

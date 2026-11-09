"""TODO 2: resume continues a run in a new process from the run store: budget, plan and history carried."""

import pytest

from faultlab.helper import Crash, Process, World, initial_plan
from faultlab.recover import ResumeRefused, resume, start
from relay.agents import Budget

TASK = {"task_id": "HT-031", "files": ["src/relay/escalation/rules.py"], "tests": "tests/test_f11.py",
        "branch": "agent/ht-031"}
BUDGET = Budget(max_steps=40, max_usd=0.50, max_seconds=600)


def test_a_paused_run_resumes_where_it_stopped_with_its_spend(tmp_path):
    world = World("none", TASK)
    first = Process(world, tmp_path / "r.db", BUDGET)
    paused = start(first, "k1")
    assert paused.status == "awaiting_approval"
    spent = first.meter.usd
    first.gate.decide(paused.approval_id, world.person("priya.n"), True, "read it")
    second = Process(world, tmp_path / "r.db", BUDGET)
    done = resume(second, first.run_id)
    assert done.status == "finished" and len(world.github.pulls) == 1
    assert second.meter.usd > spent and second.policy.pos == len(initial_plan(TASK))
    first.store.close()
    second.store.close()


def test_history_counts_across_a_restart(tmp_path):
    world = World("tool_timeout", TASK)
    procs = [Process(world, tmp_path / "t.db", BUDGET)]
    result = start(procs[0], "k2")
    assert result.reason == "repeated_failure:error:run_tests"
    cp = procs[0].store.run(procs[0].run_id)["checkpoint"]
    assert [h[2] for h in cp["history"]].count("error:run_tests") == 3
    for p in procs:
        p.store.close()


def test_a_crashed_run_resumes_with_an_empty_or_saved_checkpoint(tmp_path):
    world = World("crash_mid_edit", TASK)
    first = Process(world, tmp_path / "c.db", BUDGET)
    with pytest.raises(Crash):
        start(first, "k3")
    second = Process(world, tmp_path / "c.db", BUDGET)
    result = resume(second, first.run_id)
    assert result.reason == "repeated_failure:refused:unknown_outcome"
    first.store.close()
    second.store.close()


def test_a_final_run_is_not_resumed(tmp_path):
    world = World("kill_switch", TASK)
    first = Process(world, tmp_path / "k.db", BUDGET)
    assert start(first, "k4").status == "revoked"
    with pytest.raises(ResumeRefused):
        resume(Process(world, tmp_path / "k.db", BUDGET), first.run_id)
    first.store.close()

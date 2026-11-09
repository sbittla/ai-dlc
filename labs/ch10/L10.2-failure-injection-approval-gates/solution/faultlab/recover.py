"""Starting and resuming a helper run (resume is TODO 2)."""

from __future__ import annotations

from relay.agents import Budget, StepRecord
from relay.agents.loop import LoopResult
from relay.agents.state import FINAL

from .helper import Process, initial_plan


class ResumeRefused(Exception):
    pass


def start(proc: Process, request_key: str) -> LoopResult | None:
    """Start the run for `request_key`. A repeated request finds the existing run and starts nothing (None)."""
    if not proc.start(request_key):
        return None
    proc.attach(proc.run_id, initial_plan(proc.world.task), 0)
    return proc.drive([])


def resume(proc: Process, run_id: str) -> LoopResult:
    """Continue `run_id` in a new process from what the run store holds.

    1. Read the run (proc.store.run). If its status is in FINAL, raise ResumeRefused naming the status:
       a finished, handed-back, stopped or revoked run is not resumed.
    2. From its checkpoint: restore the meter (proc.meter.restore(checkpoint["meter"])), so the budget
       continues from what was spent; attach the policy at the saved plan and position
       (proc.attach(run_id, checkpoint["plan"], checkpoint["pos"])); and rebuild the history as
       StepRecord(tool, ok, failure, progress) from each saved list, so repeated failures count across
       the restart. A run with an empty checkpoint starts from initial_plan, position 0, empty history.
    3. Set the run's status to "running" (reason None) and return proc.drive(history).

    Between steps 1 and 2, if the run has a stored budget, set proc.meter.budget = Budget(**run["budget"]):
    the budget lives in the run, so a raise approved while it waited (ADR-026) applies when it resumes.

    Nothing else is needed for safety: the journal and the approval gate make every repeated call safe.
    """
    run = proc.store.run(run_id)
    if run["status"] in FINAL:
        raise ResumeRefused(f"run {run_id} is {run['status']}")
    if run["budget"]:
        proc.meter.budget = Budget(**run["budget"])
    cp = run["checkpoint"]
    if cp:
        proc.meter.restore(cp["meter"])
        proc.attach(run_id, cp["plan"], cp["pos"])
        history = [StepRecord(*h) for h in cp["history"]]
    else:
        proc.attach(run_id, initial_plan(proc.world.task), 0)
        history = []
    proc.store.set_status(run_id, "running", None, proc.world.clock.stamp())
    return proc.drive(history)

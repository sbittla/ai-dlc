"""Production tool contracts and handlers for agents run as workers (added in 4.30.0; ADR-049, ADR-050).

Chapter 10's contracts (`relay.agents.tools`) stay the source of truth for what each tool is. Running them in
production changes two things, and this module holds both:

- **Where code runs.** `run_tests` executes code the agent wrote. In production its handler runs that code in
  the sandbox (`relay.agentops.sandbox`), never in the worker's process. Its output can carry anything the
  code printed, including text from files an outsider wrote, so the production contract declares
  `untrusted_result` (Chapter 12's rule, ADR-034). `run_code` is the general form, for agents that compute
  with code; it has the same contract shape.
- **How often an effect happens.** `open_pull_request` is idempotent within a run (Chapter 10). Its production
  handler also goes through the effect ledger under the natural key `pr:<task>`, so a second run for the same
  task, started by a duplicate delivery, returns the pull request the first run opened instead of a second one.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from ..agents import HELPER_TOOLS, Param, ToolContract, ToolOutput
from .effects import EffectLedger
from .sandbox import SandboxPolicy, SandboxResult, run_code

RUN_TESTS_SANDBOXED = replace(HELPER_TOOLS["run_tests"], untrusted_result=True)
RUN_CODE = ToolContract(
    "run_code", "Run a short Python program in the sandbox: no network, no secrets, a throwaway directory.",
    (Param("code", "text", max_len=20000),), "read", max_result_chars=6000, untrusted_result=True)
PRODUCTION_HELPER_TOOLS = {**HELPER_TOOLS, "run_tests": RUN_TESTS_SANDBOXED}


def summarize(result: SandboxResult) -> dict:
    """What the model and the journal see of a sandbox run: status, a tail of the output, and the refusals."""
    return {"status": result.status, "exit_code": result.exit_code, "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-1000:], "refusals": [r["reason"] for r in result.refusals],
            "seconds": result.seconds}


def sandboxed_tests(files: Callable[[], dict[str, str]], runner: str, policy: SandboxPolicy,
                    on_result: Callable[[SandboxResult], None] | None = None) -> Callable[[dict], ToolOutput]:
    """A `run_tests` handler that runs `runner` (a Python program) beside the branch's files, in the sandbox.

    The failure signature is stable: `tests:<status>` for a failing or stopped run, and `sandbox:refused` when
    the code tried something the policy refuses, so three refused runs stop the agent (Chapter 10's rule).
    """
    def handler(args: dict) -> ToolOutput:
        result = run_code(runner, files(), policy)
        if on_result is not None:
            on_result(result)
        value = summarize(result)
        if result.refused:
            failure = "sandbox:refused"
        elif result.status != "ok":
            failure = f"tests:{result.status}"
        else:
            failure = None
        return ToolOutput(value, result.seconds, failure=failure, progress=f"tests:{result.status}")
    return handler


def ledgered_pull_request(ledger: EffectLedger, run_id: str, task_id: str,
                          open_pr: Callable[[str, dict], dict],
                          provider_window_s: float = 86_400.0) -> Callable[[dict], ToolOutput]:
    """An `open_pull_request` handler that opens at most one pull request per task, whatever the run.

    `open_pr(effect_key, args)` must itself look before it creates (Chapter 10), and should pass the key to
    the code host where it can. The derived `diff_sha256` is part of the recorded arguments, so a second run
    with a different diff for the same task is refused as a conflict, for a person to resolve.
    """
    def handler(args: dict) -> ToolOutput:
        recorded = {"task": task_id, "diff_sha256": args.get("diff_sha256")}
        result, replayed = ledger.perform(f"pr:{task_id}", "pull_request", recorded, run_id,
                                          lambda key, _a: open_pr(key, args), provider_idempotent=True,
                                          provider_window_s=provider_window_s)
        return ToolOutput({**result, "replayed": replayed}, 1.0, progress=f"pr:{result.get('number')}")
    return handler

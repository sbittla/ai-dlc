"""Traces of agent runs, rebuilt from the run journal, and the alerts they feed (added in 4.27.0; ADR-036).

Chapter 10's runtime keeps a durable journal: `agent_runs` (status, stop reason) and `agent_steps` (one row per
tool call, with its outcome). `trace_run` turns one run and its steps into a trace that follows the GenAI
conventions: an `invoke_agent` span for the run and one `execute_tool` span per step. The run ID links the
trace to the journal and to the audit trail, so the trace carries no person and no arguments: the person a
run acts for is in the audit trail (400 days, restricted), and arguments appear only as their SHA-256.

`run_signals` counts what the alert rules read: runs stopped by a budget (AL-004) and steps refused as
`unknown_outcome`, where an effect may or may not have happened and a person must check (AL-005).

The functions take the dictionaries `RunStore.run` and `RunStore.steps` return; this module does not import
the agent runtime's package.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from . import semconv
from .trace import ERROR, INTERNAL, OK


def _ns(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1_000_000_000)


def stop_kind(run: dict) -> str:
    reason = run.get("reason") or ""
    if run["status"] == "stopped" and reason.startswith("budget:"):
        return "budget"
    return run["status"]


def trace_run(tracer, meter, run: dict, steps: list[dict]):
    """Export one run as a trace; returns the root span."""
    root = tracer.start(f"invoke_agent {run['agent_id']}", INTERNAL, start_ns=_ns(run["created_at"]), attributes={
        semconv.GEN_AI_OPERATION_NAME: "invoke_agent", semconv.GEN_AI_AGENT_ID: run["agent_id"],
        semconv.GEN_AI_AGENT_NAME: run["agent_id"], semconv.RELAY_AGENT_RUN_ID: run["run_id"],
        semconv.RELAY_AGENT_DESIGN: run.get("design", ""), semconv.RELAY_AGENT_STATUS: run["status"],
        semconv.RELAY_AGENT_STOP_REASON: run.get("reason") or "",
        "on_behalf_of": run.get("on_behalf_of")})  # not on the allowlist: dropped, and counted, at export
    for i, step in enumerate(steps):
        start = _ns(step["at"])
        nxt = _ns(steps[i + 1]["at"]) if i + 1 < len(steps) else _ns(run["updated_at"])
        code = (step.get("result") or {}).get("code") if isinstance(step.get("result"), dict) else None
        span = tracer.start(f"execute_tool {step['tool']}", INTERNAL, parent=root, start_ns=start, attributes={
            semconv.GEN_AI_OPERATION_NAME: "execute_tool", semconv.GEN_AI_TOOL_NAME: step["tool"],
            semconv.RELAY_STEP_SEQ: step["seq"], semconv.RELAY_STEP_OUTCOME: step["outcome"],
            semconv.RELAY_ARGS_SHA256: step["args_sha256"], semconv.RELAY_STEP_CODE: code or ""})
        tracer.end(span, ERROR if step["outcome"] in ("error", "refused") else OK, end_ns=max(start, nxt))
    runs = meter.counter("relay.agent.runs", "{run}", "finished agent runs by agent and how they ended", limit=100)
    runs.add(1, {semconv.GEN_AI_AGENT_ID: run["agent_id"], semconv.RELAY_AGENT_STATUS: stop_kind(run)})
    unknown = sum(1 for s in steps if s["outcome"] == "refused" and isinstance(s.get("result"), dict)
                  and s["result"].get("code") == "unknown_outcome")
    if unknown:
        meter.counter("relay.agent.unknown_outcome", "{step}", "steps refused as unknown_outcome",
                      limit=100).add(unknown, {semconv.GEN_AI_AGENT_ID: run["agent_id"]})
    final_error = run["status"] in ("stopped", "failed", "revoked")
    return tracer.end(root, ERROR if final_error else OK, end_ns=_ns(run["updated_at"]))


def run_signals(runs: list[dict], steps_by_run: dict[str, list[dict]]) -> dict:
    """Budget stops per agent and `unknown_outcome` refusals per agent: AL-004 and AL-005's inputs."""
    budget, unknown = Counter(), Counter()
    for run in runs:
        if stop_kind(run) == "budget":
            budget[run["agent_id"]] += 1
        for step in steps_by_run.get(run["run_id"], []):
            result = step.get("result")
            if step["outcome"] == "refused" and isinstance(result, dict) and result.get("code") == "unknown_outcome":
                unknown[run["agent_id"]] += 1
    return {"relay.agent.budget_stops": dict(budget), "relay.agent.unknown_outcome": dict(unknown)}

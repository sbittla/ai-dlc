"""Replay the opening incident's five-agent pipeline, with and without Relay 4.24.0's controls (provided).

The pipeline: a supervisor, a planner, a coder, a tester and a reviewer. Every agent received the whole
shared transcript on every call (transcript hand-offs), its framework put a fresh timestamp at the top of
each prompt (so no prefix was ever reused from a cache), and its only stopping condition was the
reviewer's approval. The reviewer never approved: it asked each round for a 403 that an approved test
owned by @relay/security forbids, and the coder may not change that test. The job ran until GitHub
Actions cancelled it at its six-hour limit.

`replay("none")` reproduces that run call by call. `replay("full")` runs the same loop with the multi-agent
design's dev-calibrated budget, Relay's repeated-failure stop and summary hand-offs. `replay("repeat_only")`
keeps summary hand-offs and the repeated-failure stop but no budget, to show what the stop rule alone does.

The replay's length is not independent evidence. Its token sizes (data/incident/pipeline.json), the window of
one million tokens and the assumed prompt-processing rate (40,000 input tokens per second, data/simulator.json)
were chosen so that the loop fills GitHub's six-hour limit, as the composite incident did. The report prints
what the same loop does at half that rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from relay.agents import Budget, BudgetExceeded, Meter, StepRecord, StopRules, stop_reason

from . import DATA_DIR
from .runtime import load_json


@dataclass
class Replay:
    controls: str
    status: str
    reason: str
    rounds: int
    calls: int
    input_tokens: int
    output_tokens: int
    usd: float
    seconds: float
    largest_input: int
    by_agent_usd: dict = field(default_factory=dict)
    by_agent_calls: dict = field(default_factory=dict)
    commits: int = 0
    review_comments: int = 0
    round_usd: list = field(default_factory=list)
    round_start_tokens: list = field(default_factory=list)


MODES = ("none", "full", "repeat_only")


def replay(mode: str, input_tokens_per_s: float | None = None) -> Replay:
    if mode not in MODES:
        raise ValueError(mode)
    controls = mode != "none"
    cfg = load_json(DATA_DIR / "incident" / "pipeline.json")
    lat = dict(load_json(DATA_DIR / "simulator.json")["latency"])
    if input_tokens_per_s is not None:  # sensitivity: the replay's length depends on this assumed rate
        lat["input_tokens_per_s"] = input_tokens_per_s
    ctl = cfg["controls"]
    unlimited = Budget(max_steps=10**9, max_usd=10**9, max_seconds=10**9)
    budget = Budget(**ctl["budget"]) if mode == "full" else unlimited
    meter = Meter(budget)
    rules = StopRules(repeat_limit=ctl["repeat_limit"])
    history: list[StepRecord] = []
    base = cfg["system_tokens"] + cfg["task_tokens"]
    shared = 0                       # the transcript every agent receives (no controls)
    own = {a["agent"]: 0 for a in cfg["round"]}  # each agent's own context (controls: summaries only)
    clock = 0.0
    calls: dict[str, int] = {}
    largest = 0
    out = Replay(mode, "", "", 0, 0, 0, 0, 0.0, 0.0, 0)

    def call(agent: str, context: int, output: int) -> bool:
        """One model call; False if the job limit or the budget stops it before it starts."""
        nonlocal clock, largest
        input_tokens = min(base + context, cfg["window_tokens"])
        seconds = round(lat["base_s"] + input_tokens / lat["input_tokens_per_s"] + output / lat["output_tokens_per_s"], 3)
        if clock + seconds > cfg["job_limit_s"]:
            out.status, out.reason = "cancelled", "GitHub Actions job limit (6 hours)"
            return False
        if mode == "full":
            meter.admit(meter.estimate(cfg["model"], input_tokens, ctl["max_output"]))
        meter.charge_model(agent, cfg["model"], input_tokens, output, seconds)
        clock += seconds
        largest = max(largest, input_tokens)
        calls[agent] = calls.get(agent, 0) + 1
        return True

    try:
        p = cfg["planner"]
        if not call("planner", 0, p["output"]):
            raise StopIteration
        clock += p["tool_s"]
        shared += p["output"] + p["read_tokens"]
        for agent in own:
            own[agent] = ctl["summary_tokens"] + (p["read_tokens"] if agent in ("coder", "reviewer") else 0)
        while True:
            if controls:
                reason = stop_reason(meter, history, rules)
                if reason is not None:
                    out.status, out.reason = "handed_back", reason
                    break
            out.rounds += 1
            usd_before = meter.usd
            out.round_start_tokens.append(min(base + shared, cfg["window_tokens"]) if not controls
                                          else max(base + c for c in own.values()))
            for step in cfg["round"]:
                agent = step["agent"]
                context = own[agent] if controls else shared
                if not call(agent, context, step["output"]):
                    raise StopIteration
                added = step["output"] + step.get("result", 0)
                if "tool" in step:
                    clock += step["tool_s"]
                    meter.charge_tool(agent, step["tool_s"])
                    if step["tool"] == "edit_file":
                        out.commits += 1
                if "finding" in step:
                    out.review_comments += 1
                    history.append(StepRecord("review", False, step["finding"], f"round:{out.rounds}"))
                if controls:
                    own[agent] += added
                    for other in own:
                        if other != agent:
                            own[other] += ctl["summary_tokens"]
                else:
                    shared += added
            out.round_usd.append(meter.usd - usd_before)
    except StopIteration:
        pass
    except BudgetExceeded as exc:
        out.status, out.reason = "stopped", f"budget:{exc.kind}"
    out.calls = meter.model_calls
    out.input_tokens, out.output_tokens = meter.input_tokens, meter.output_tokens
    out.usd, out.seconds, out.largest_input = meter.usd, clock, largest
    out.by_agent_usd = dict(meter.by_actor)
    out.by_agent_calls = calls
    return out

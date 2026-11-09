"""Optional: one workflow step with a real Claude model (provided; never needed, never run by the tests).

    pip install -e ".[live]"            # the pinned Anthropic SDK; credentials in ANTHROPIC_API_KEY
    RELAY_LAB_LIVE=1 python -m agentlab.report live --task HT-031                       # bash
    $env:RELAY_LAB_LIVE="1"; python -m agentlab.report live --task HT-031; Remove-Item Env:RELAY_LAB_LIVE

It sends the workflow's implement prompt for one task (the task, its file list and the sizes of its files,
not the files themselves) and reports tokens, latency and cost, so you can compare a real call's shape
with the simulator's assumptions. The cost is estimated before the call and refused above
COST_CEILING_USD. API errors, refusals and truncation are returned as outcomes, not raised: a reply
cut off at MAX_TOKENS shows stop_reason=max_tokens. Effort is set low, as in Lab 2.1, because the
model's thinking also counts against MAX_TOKENS.
"""

from __future__ import annotations

import os
import time

from relay.agents import DEFAULT_PRICES, cost_usd

from . import DATA_DIR
from .world import load_tasks

MODEL = "claude-opus-5-5"
COST_CEILING_USD = 0.50
MAX_TOKENS = 2048


def prompt_for(task) -> str:
    files = "\n".join(f"- {p} ({task.tokens[p]} tokens)" for p in task.files)
    return (f"You are implementing task {task.task_id} ('{task.title}') in Relay. You may edit only:\n{files}\n"
            f"The approved tests are in {task.tests} and must not change. If the task cannot be done within these "
            f"files, reply CANNOT and say which file you would need. Otherwise describe the change in under 200 words.")


def run_live(task_id: str) -> str:
    if os.environ.get("RELAY_LAB_LIVE") != "1":
        return "live mode is off: set RELAY_LAB_LIVE=1 to call the API"
    task = next(t for t in load_tasks(DATA_DIR / "tasks.jsonl") if t.task_id == task_id)
    prompt = prompt_for(task)
    estimate = cost_usd(DEFAULT_PRICES[MODEL], len(prompt) // 4, MAX_TOKENS)
    if estimate > COST_CEILING_USD:
        return f"refused_cost: estimated ${estimate:.3f} is above ${COST_CEILING_USD:.2f}"
    import anthropic  # imported lazily so offline runs need no package

    started = time.perf_counter()
    try:
        response = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                                         output_config={"effort": "low"},  # as in Lab 2.1
                                                         messages=[{"role": "user", "content": prompt}])
    except anthropic.APIError as exc:
        return f"api_error:{type(exc).__name__}"
    seconds = time.perf_counter() - started
    used = cost_usd(DEFAULT_PRICES[MODEL], response.usage.input_tokens, response.usage.output_tokens)
    text = "".join(b.text for b in response.content if b.type == "text")
    return (f"stop_reason={response.stop_reason} input={response.usage.input_tokens} "
            f"output={response.usage.output_tokens} seconds={seconds:.1f} cost=${used:.4f}\n\n{text}")

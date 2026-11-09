"""Optional: ask a Claude model to review one pull request against the checklist (provided; never needed).

    pip install -e ".[live]"            # the pinned Anthropic SDK; credentials in ANTHROPIC_API_KEY
    RELAY_LAB_LIVE=1 python -m prkit.report live-review --pr PR-5      # bash
    $env:RELAY_LAB_LIVE="1"; python -m prkit.report live-review --pr PR-5; Remove-Item Env:RELAY_LAB_LIVE

The adapter follows Lab 2.1's and Lab 4.2's: the official SDK, imported
lazily so offline runs need no package, and API errors, refusals and
truncation returned as outcomes rather than exceptions. Nothing in the lab's
tests or golden files calls it. The cost of one review is estimated before
the call from the prompt's length and refused above COST_CEILING_USD.

AI-assisted review is a second reader, not an approval. Section 9.4 explains
its blind spots; compare what it says with the checklist, and record both.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

MODEL = "claude-opus-5-5"
PRICES = {"claude-opus-5-5": (4.00, 20.00)}  # USD per million tokens (input, output); from Lab 2.1; verify before use
COST_CEILING_USD = 0.50
MAX_TOKENS = 2048


@dataclass(frozen=True)
class Review:
    text: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    stop_reason: str  # end_turn, max_tokens (truncated), refusal, api_error:<name>, or refused_cost


def estimate_cost(prompt: str, model: str = MODEL) -> float:
    """A rough upper estimate: four characters per input token, and the full output budget."""
    p_in, p_out = PRICES[model]
    return (len(prompt) / 4) * p_in / 1e6 + MAX_TOKENS * p_out / 1e6


@dataclass
class ClaudeReviewer:
    model: str = MODEL
    _client: object = field(default=None, init=False, repr=False)

    def review(self, checklist: str, diff_text: str) -> Review:
        if os.environ.get("RELAY_LAB_LIVE") != "1":
            raise RuntimeError("live mode is off: set RELAY_LAB_LIVE=1 to call the API")
        prompt = (f"Review this pull request against the checklist. For each item, say pass, fail or cannot tell, "
                  f"and quote the line that decides it.\n\nChecklist:\n{checklist}\n\nDiff:\n{diff_text}")
        if estimate_cost(prompt, self.model) > COST_CEILING_USD:
            return Review("", 0, 0, 0.0, "refused_cost")
        import anthropic  # imported lazily so offline runs need no package

        if self._client is None:
            self._client = anthropic.Anthropic()
        started = time.perf_counter()
        try:
            response = self._client.messages.create(model=self.model, max_tokens=MAX_TOKENS,
                                                    messages=[{"role": "user", "content": prompt}])
        except anthropic.APIError as exc:
            return Review("", 0, 0, round(time.perf_counter() - started, 3), f"api_error:{type(exc).__name__}")
        text = "".join(b.text for b in response.content if b.type == "text")
        return Review(text, response.usage.input_tokens, response.usage.output_tokens,
                      round(time.perf_counter() - started, 3), response.stop_reason or "")

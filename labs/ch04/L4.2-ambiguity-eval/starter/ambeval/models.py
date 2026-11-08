"""Optional live detector: a Claude model classifies each statement (provided).

The adapter follows Lab 2.1's live adapter (`labs/ch02/L2.1-model-eval-harness/
solution/harness/models.py`): the official Anthropic SDK, structured output
constrained to a JSON schema, and API errors returned as outcomes instead of
exceptions. It deliberately does not enable server-side refusal fallbacks: an
evaluation must know which model produced each answer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .prompt import DEFECT_SCHEMA


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    stop_reason: str = "end_turn"


@dataclass
class ClaudeModel:
    """Live adapter. Requires `pip install -e ".[live]"` and credentials
    (ANTHROPIC_API_KEY, or an `ant auth login` profile)."""

    name: str  # an exact model ID, e.g. "claude-opus-5-5" or "claude-haiku-5-5"
    price_in_per_mtok: float
    price_out_per_mtok: float
    effort: str = "low"  # classification rarely benefits from higher effort; measure it
    _client: object = field(default=None, init=False, repr=False)

    def complete(self, system: str, user: str) -> Completion:
        import anthropic  # imported lazily so offline runs need no package

        if self._client is None:
            self._client = anthropic.Anthropic()
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self.name,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": DEFECT_SCHEMA},
                },
            )
        except anthropic.APIError as exc:
            # After the SDK's own retries. Record the failure instead of losing the run.
            return Completion("", 0, 0, round(time.perf_counter() - started, 3),
                              stop_reason=f"api_error:{type(exc).__name__}")
        latency = time.perf_counter() - started
        text = next((b.text for b in response.content if b.type == "text"), "")
        return Completion(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=round(latency, 3),
            stop_reason=response.stop_reason or "",
        )


LIVE_PRICES = {  # USD per million tokens (input, output); copied from Lab 2.1; verify before use
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def live_model(model_id: str) -> ClaudeModel:
    if model_id not in LIVE_PRICES:
        raise ValueError(f"add a price for {model_id} to LIVE_PRICES first")
    p_in, p_out = LIVE_PRICES[model_id]
    return ClaudeModel(name=model_id, price_in_per_mtok=p_in, price_out_per_mtok=p_out)

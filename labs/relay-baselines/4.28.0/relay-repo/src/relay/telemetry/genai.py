"""Spans and metrics for model calls, following the GenAI semantic conventions (added in 4.27.0; ADR-036).

A model call is recorded with what it was (provider, operation, requested and returned model, prompt version
and its hash), what it cost in tokens, how long it took and why it stopped. It is never recorded with what it
said. `model_call` accepts a `content` argument only so that a caller who passes one is counted: the content
is dropped, and `content_dropped` says how often someone tried. Instrumentation libraries that offer to
capture message content (often behind an environment variable) must leave it off in Relay (ADR-023, ADR-036).
"""

from __future__ import annotations

from . import semconv
from .trace import CLIENT, ERROR, OK

# The bucket boundaries the GenAI conventions recommend (tokens; seconds).
TOKEN_BUCKETS = (1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864)
DURATION_BUCKETS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92)


class ModelCallTelemetry:
    def __init__(self, tracer, meter) -> None:
        self.tracer = tracer
        self.tokens = meter.histogram(semconv.GEN_AI_CLIENT_TOKEN_USAGE, "{token}", "tokens per model call",
                                      limit=50, boundaries=TOKEN_BUCKETS)
        self.duration = meter.histogram(semconv.GEN_AI_CLIENT_OPERATION_DURATION, "s", "model call duration",
                                        limit=50, boundaries=DURATION_BUCKETS)
        self.content_dropped = 0

    def model_call(self, *, provider: str, operation: str, request_model: str, response_model: str,
                   input_tokens: int, output_tokens: int, finish_reason: str, start_ns: int, duration_s: float,
                   prompt_version: str, prompt_sha256: str, error: str | None = None, parent=None, content=None):
        if content is not None:
            self.content_dropped += 1
        attrs = {semconv.GEN_AI_OPERATION_NAME: operation, semconv.GEN_AI_PROVIDER_NAME: provider,
                 semconv.GEN_AI_REQUEST_MODEL: request_model, semconv.GEN_AI_RESPONSE_MODEL: response_model,
                 semconv.GEN_AI_USAGE_INPUT_TOKENS: input_tokens, semconv.GEN_AI_USAGE_OUTPUT_TOKENS: output_tokens,
                 semconv.GEN_AI_RESPONSE_FINISH_REASONS: [finish_reason],
                 semconv.RELAY_PROMPT_VERSION: prompt_version, semconv.RELAY_PROMPT_SHA256: prompt_sha256}
        if error:
            attrs[semconv.ERROR_TYPE] = error
        span = self.tracer.start(f"{operation} {request_model}", CLIENT, parent=parent, attributes=attrs,
                                 start_ns=start_ns)
        common = {semconv.GEN_AI_OPERATION_NAME: operation, semconv.GEN_AI_PROVIDER_NAME: provider,
                  semconv.GEN_AI_REQUEST_MODEL: request_model}
        self.tokens.record(input_tokens, {**common, semconv.GEN_AI_TOKEN_TYPE: "input"})
        self.tokens.record(output_tokens, {**common, semconv.GEN_AI_TOKEN_TYPE: "output"})
        self.duration.record(duration_s, {**common, **({semconv.ERROR_TYPE: error} if error else {})})
        return self.tracer.end(span, ERROR if error else OK, end_ns=start_ns + int(duration_s * 1e9))

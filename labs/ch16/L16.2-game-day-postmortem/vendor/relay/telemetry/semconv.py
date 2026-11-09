"""The attribute and metric names Relay's telemetry may use (added in 4.27.0; ADR-036).

Names follow the OpenTelemetry semantic conventions as published in late 2026. The HTTP conventions are
stable. The database conventions were stabilised more recently, and the generative-AI (GenAI) conventions
are still in Development status: their names have changed between releases (for example `gen_ai.system`
became `gen_ai.provider.name`) and may change again. Check this file against the conventions before
every upgrade of a collector or a backend that interprets them.

`ALLOWED` is an allowlist. An attribute whose key is not in it is dropped by `relay.telemetry.redact`
before export, so a new attribute is a reviewed change to this file, not a side effect of new code.
`CONTENT_KEYS` are the GenAI attributes that would carry prompts, responses or tool arguments. Relay never
records them, whatever an instrumentation library's settings say.
"""

from __future__ import annotations

SCHEMA_NOTE = ("OpenTelemetry semantic conventions as published in late 2026; HTTP stable, GenAI in "
               "Development status. Re-check before upgrading (ADR-036).")

# ------------------------------------------------------------------ resource
SERVICE_NAME = "service.name"
SERVICE_VERSION = "service.version"
DEPLOYMENT_ENVIRONMENT = "deployment.environment.name"

# ------------------------------------------------------------------ HTTP (stable)
HTTP_REQUEST_METHOD = "http.request.method"
HTTP_ROUTE = "http.route"
HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"
ERROR_TYPE = "error.type"
HTTP_SERVER_REQUEST_DURATION = "http.server.request.duration"  # histogram, seconds
KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "CONNECT", "TRACE"})
OTHER_METHOD = "_OTHER"
# The explicit bucket boundaries the HTTP conventions recommend for request duration, in seconds.
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)

# ------------------------------------------------------------------ database
DB_SYSTEM_NAME = "db.system.name"
DB_OPERATION_NAME = "db.operation.name"
DB_COLLECTION_NAME = "db.collection.name"

# ------------------------------------------------------------------ GenAI (Development status)
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"        # chat, invoke_agent, execute_tool, ...
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOKEN_TYPE = "gen_ai.token.type"                 # input or output, on the token-usage histogram
GEN_AI_CLIENT_TOKEN_USAGE = "gen_ai.client.token.usage"                # histogram, tokens
GEN_AI_CLIENT_OPERATION_DURATION = "gen_ai.client.operation.duration"  # histogram, seconds

# Attributes that would carry content. Never recorded (ADR-023, ADR-036).
CONTENT_KEYS = frozenset({
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions",
    "gen_ai.prompt", "gen_ai.completion", "gen_ai.tool.call.arguments", "gen_ai.tool.call.result",
    "gen_ai.tool.definitions",
})

# ------------------------------------------------------------------ Relay's own namespace
RELAY_PROMPT_VERSION = "relay.prompt.version"
RELAY_PROMPT_SHA256 = "relay.prompt.sha256"
RELAY_AGENT_RUN_ID = "relay.agent.run_id"
RELAY_AGENT_STATUS = "relay.agent.status"
RELAY_AGENT_STOP_REASON = "relay.agent.stop_reason"
RELAY_AGENT_DESIGN = "relay.agent.design"
RELAY_STEP_SEQ = "relay.step.seq"
RELAY_STEP_OUTCOME = "relay.step.outcome"
RELAY_STEP_CODE = "relay.step.code"
RELAY_ARGS_SHA256 = "relay.args.sha256"
RELAY_WORKER_OUTCOME = "relay.worker.outcome"
RELAY_ESCALATION_RESULT = "relay.escalation.result"
RELAY_SECURITY_EVENT = "relay.security.event"            # auth.failure, rate_limited, forbidden
RELAY_CLIENT_NETWORK = "relay.client.network"            # a /24 (IPv4) or /48 (IPv6) prefix, never an address
RELAY_CREDENTIAL_FINGERPRINT = "relay.credential.fingerprint"  # keyed hash; never the credential
RELAY_SLI_GOOD = "relay.sli.good"
RELAY_SLO_ID = "relay.slo.id"
RELAY_TRIAGE_OUTCOME = "relay.triage.outcome"
OVERFLOW = "otel.metric.overflow"                        # the series that absorbs attribute sets over the limit

ALLOWED = frozenset({
    SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT,
    HTTP_REQUEST_METHOD, HTTP_ROUTE, HTTP_RESPONSE_STATUS_CODE, ERROR_TYPE,
    DB_SYSTEM_NAME, DB_OPERATION_NAME, DB_COLLECTION_NAME,
    GEN_AI_OPERATION_NAME, GEN_AI_PROVIDER_NAME, GEN_AI_REQUEST_MODEL, GEN_AI_RESPONSE_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS, GEN_AI_USAGE_OUTPUT_TOKENS, GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_AGENT_ID, GEN_AI_AGENT_NAME, GEN_AI_TOOL_NAME, GEN_AI_TOOL_CALL_ID, GEN_AI_TOKEN_TYPE,
    RELAY_PROMPT_VERSION, RELAY_PROMPT_SHA256, RELAY_AGENT_RUN_ID, RELAY_AGENT_STATUS, RELAY_AGENT_STOP_REASON,
    RELAY_AGENT_DESIGN, RELAY_STEP_SEQ, RELAY_STEP_OUTCOME, RELAY_STEP_CODE, RELAY_ARGS_SHA256,
    RELAY_WORKER_OUTCOME, RELAY_ESCALATION_RESULT, RELAY_SECURITY_EVENT, RELAY_CLIENT_NETWORK,
    RELAY_CREDENTIAL_FINGERPRINT, RELAY_SLI_GOOD, RELAY_SLO_ID, RELAY_TRIAGE_OUTCOME, OVERFLOW,
})

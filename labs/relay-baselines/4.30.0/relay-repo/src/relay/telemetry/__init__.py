"""Relay's telemetry: traces, metrics and logs, redaction, SLOs, alerting and detection (added in 4.27.0).

Standard library only (ADR-036). The data model and the export format are OpenTelemetry's, so the
OpenTelemetry Collector and any backend that accepts OTLP can read what Relay writes, but this is not the
OpenTelemetry SDK. Nothing here makes a network call: processes write OTLP JSON lines to a local directory
and the collector beside them ships the data (`infra/monitoring/collector.yaml`).

Modules: `semconv` (the allowlist of names), `redact`, `trace`, `metrics`, `logs`, `otlp` (encoding and
exporters), `genai` (model calls), `runs` (agent-run traces), `worker` (the worker, observed from outside),
`slo` (SLOs, budgets and burn-rate alerts, ADR-037), `fitness` (runtime fitness checks, ADR-037),
`detection` and `alerting` (detection rules, routing and paging, ADR-038).

The package imports only the standard library, `relay.audit` (redaction, the trail's verifier),
`relay.escalation`'s public interface (for RF-001) and itself; `tests/test_telemetry_architecture.py`
enforces it. `relay.service` imports it for the HTTP middleware; neither the worker nor the agent runtime does.
"""

from .logs import Logger, LogRecord
from .metrics import Meter
from .otlp import FileExporter, MemoryExporter
from .redact import clean_attributes, redact_text
from .trace import IdSource, Span, Tracer, format_traceparent, parse_traceparent

__all__ = ["FileExporter", "IdSource", "LogRecord", "Logger", "MemoryExporter", "Meter", "Span", "Tracer",
           "clean_attributes", "format_traceparent", "parse_traceparent", "redact_text"]

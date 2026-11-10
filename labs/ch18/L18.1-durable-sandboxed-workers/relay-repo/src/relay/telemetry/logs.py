"""Structured logs with trace context (added in 4.27.0; ADR-036).

A log record has a time, a severity, a body and attributes, and the trace and span it was written in, so a
log line links to its trace. The body is redacted like any attribute value, and attributes pass the key
allowlist. Relay's convention (AGENTS.md) still holds: never log a token, a request header or a request body.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .redact import clean_attributes, redact_text

# OpenTelemetry's severity numbers for the text levels Relay uses.
SEVERITY = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17, "FATAL": 21}


@dataclass
class LogRecord:
    time_ns: int
    severity_text: str
    body: str
    attributes: dict = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None

    @property
    def severity_number(self) -> int:
        return SEVERITY[self.severity_text]


class Logger:
    def __init__(self, exporter, clock_ns: Callable[[], int] = time.time_ns) -> None:
        self.exporter, self.clock_ns = exporter, clock_ns
        self.redactions: Counter = Counter()

    def emit(self, severity: str, body: str, attributes: dict | None = None, span=None,
             at_ns: int | None = None) -> LogRecord:
        if severity not in SEVERITY:
            raise ValueError(severity)
        clean_body, _ = redact_text(body, self.redactions)
        clean_attrs, _ = clean_attributes(dict(attributes or {}), self.redactions)
        record = LogRecord(self.clock_ns() if at_ns is None else at_ns, severity, clean_body, clean_attrs,
                           span.trace_id if span else None, span.span_id if span else None)
        self.exporter.export_log(record)
        return record

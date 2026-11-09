"""Traces: spans, a tracer and W3C trace context, on the standard library (added in 4.27.0; ADR-036).

The model is OpenTelemetry's: a trace is a tree of spans sharing a 16-byte trace ID; each span has an
8-byte span ID, a parent, a kind, start and end times in nanoseconds, attributes, events, links and a
status. Spans are exported in OTLP's JSON form by `relay.telemetry.otlp`, so any OpenTelemetry collector
can receive them. This is not the OpenTelemetry SDK; ADR-036 records why, and what would change that.

Every attribute passes `relay.telemetry.redact.clean_attributes` when the span ends, so a span cannot
export an unreviewed key or an unredacted value.

Trace context from outside is untrusted input. `parse_traceparent` accepts only a well-formed W3C
`traceparent` header, and the service does not continue an external caller's trace: it starts its own
and records the caller's context as a link (`relay.service.telemetry`).
"""

from __future__ import annotations

import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .redact import clean_attributes, redact_text

INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER = "INTERNAL", "SERVER", "CLIENT", "PRODUCER", "CONSUMER"
UNSET, OK, ERROR = "UNSET", "OK", "ERROR"
_TRACEPARENT = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    kind: str
    start_ns: int
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    links: list = field(default_factory=list)
    end_ns: int | None = None
    status: str = UNSET
    status_message: str = ""

    def set(self, key: str, value) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, at_ns: int, attributes: dict | None = None) -> None:
        self.events.append({"name": name, "time_ns": at_ns, "attributes": dict(attributes or {})})

    @property
    def duration_s(self) -> float:
        return 0.0 if self.end_ns is None else (self.end_ns - self.start_ns) / 1e9


class IdSource:
    """Trace and span IDs. Seeded for tests and labs; `random.SystemRandom` in production."""

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed) if seed is not None else random.SystemRandom()

    def _hex(self, nbytes: int) -> str:
        while True:
            value = self.rng.getrandbits(nbytes * 8)
            if value:  # all-zero IDs are invalid in W3C trace context
                return f"{value:0{nbytes * 2}x}"

    def trace_id(self) -> str:
        return self._hex(16)

    def span_id(self) -> str:
        return self._hex(8)


def parse_traceparent(header: str | None) -> dict | None:
    """The context in a W3C `traceparent` header, or None if it is missing or malformed."""
    if not header:
        return None
    m = _TRACEPARENT.match(header.strip())
    if not m:
        return None
    version, trace_id, span_id, flags = m.groups()
    if version == "ff" or set(trace_id) == {"0"} or set(span_id) == {"0"}:
        return None
    return {"trace_id": trace_id, "span_id": span_id, "sampled": int(flags, 16) & 1 == 1}


def format_traceparent(span: Span, sampled: bool = True) -> str:
    return f"00-{span.trace_id}-{span.span_id}-{'01' if sampled else '00'}"


class Tracer:
    """Starts and ends spans, cleans their attributes, and hands finished spans to an exporter."""

    def __init__(self, exporter, ids: IdSource | None = None, clock_ns: Callable[[], int] = time.time_ns) -> None:
        self.exporter, self.ids, self.clock_ns = exporter, ids or IdSource(), clock_ns
        self.redactions: Counter = Counter()

    def start(self, name: str, kind: str = INTERNAL, parent: Span | None = None, attributes: dict | None = None,
              start_ns: int | None = None, links: list | None = None) -> Span:
        return Span(name=name, trace_id=parent.trace_id if parent else self.ids.trace_id(),
                    span_id=self.ids.span_id(), parent_span_id=parent.span_id if parent else None, kind=kind,
                    start_ns=self.clock_ns() if start_ns is None else start_ns,
                    attributes=dict(attributes or {}), links=list(links or []))

    def end(self, span: Span, status: str | None = None, message: str = "", end_ns: int | None = None) -> Span:
        span.end_ns = self.clock_ns() if end_ns is None else end_ns
        if status is not None:
            span.status = status
        span.status_message, _ = redact_text(message, self.redactions) if message else ("", None)
        span.attributes, _ = clean_attributes(span.attributes, self.redactions)
        for event in span.events:
            event["attributes"], _ = clean_attributes(event["attributes"], self.redactions)
        self.exporter.export_span(span)
        return span

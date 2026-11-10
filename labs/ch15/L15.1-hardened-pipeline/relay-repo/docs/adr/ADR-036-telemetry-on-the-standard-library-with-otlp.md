# ADR-036 — Telemetry on the standard library, in OpenTelemetry's model and OTLP's format, minimised and redacted

Status: accepted
Date: 2027-02-08
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N07, ESC-N09, CON-1, CON-4
Related: ADR-008, ADR-021, ADR-023, ADR-028, ADR-031
Revisit when: an OpenTelemetry SDK release for Python is admitted to the mirror under ADR-028 with its exporter
dependencies; or the GenAI semantic conventions leave Development status. Review by 2027-08-08 in any case.
Supersedes: none.

## Context

On 2 February 2027 an incident assistant named a deploy as the cause of a latency incident while a
credential-stuffing attack continued (Chapter 16). Relay had request logs and a latency dashboard, but no
traces, no per-route metrics, no security events from the service, and no rule about what telemetry may hold.
ADR-023 kept prompts and bodies out of the audit trail; nothing applied the same rule to telemetry.

Relay is standard library only (ADR-008, AR5), and only the service may make network calls (AR4).

## Options considered

### Option A — Relay's own small telemetry package in OpenTelemetry's data model, writing OTLP JSON files that a collector sidecar ships

### Option B — Admit the OpenTelemetry SDK and an OTLP exporter through the mirror, and instrument with it

### Option C — Structured logs only, with metrics derived from them in the backend

## Decision

Option A.

- `relay.telemetry` implements spans, metrics and logs with OpenTelemetry's concepts and names, and writes OTLP
  JSON lines to a task-local directory. A collector in the same task reads them (`infra/monitoring/`).
- Minimisation first: only keys in `semconv.ALLOWED` leave the process; GenAI content attributes are never
  recorded; routes are templates; client addresses become /24 or /48 prefixes; credentials become keyed
  fingerprints. Redaction second: every value passes `relay.telemetry.redact`, which layers decoding (percent,
  HTML entities, escapes, base64, hex, full-width and zero-width characters) and national phone formats over
  `relay.audit.redact`. The collector repeats both as defence in depth.
- Incoming trace context is a span link, never a parent.
- Telemetry retention is 30 days, as ADR-023 set for traces.
- This tightens ADR-023 and Chapter 14's data map, which allowed traces to keep a redacted excerpt of a prompt.
  From 4.27.0 telemetry keeps no prompt or response text at all, redacted or not; a prompt is identified by its
  version and SHA-256. The DPIA's trace flow is updated to "no content" (owner aisha.r, with the data
  protection officer).

## Consequences

- No new dependency. The package is small enough to review, and its names match the conventions, so a
  collector and any OTLP backend can read the output.
- Relay owns code the SDK would have given it, and must follow the conventions by hand. `semconv.py` says
  which version it follows; the GenAI names are in Development status and will change.
- Instrumentation libraries for third-party code are out of reach; Relay has none to instrument yet.
- RF-003 scans exported telemetry, and AL-007 pages the security on-call if it finds anything. The monitor runs
  the scan over the files it reads on every run.
- The tracing backend is not chosen yet; the gateway's trace exporter points at a placeholder.

## Rejected alternatives

### Option B — Admit the OpenTelemetry SDK and an OTLP exporter through the mirror, and instrument with it
Rejected because: the SDK and an OTLP exporter bring several packages that each need ADR-028's review and hash pinning, for features Relay would not use yet, and they would break AR5.
Revisit if: Relay instruments third-party libraries, or needs tail sampling in process; then admit the SDK through the mirror under ADR-028.

### Option C — Structured logs only, with metrics derived from them in the backend
Rejected because: logs alone carry no trace structure, so an assistant or a person cannot follow one request across the service, the worker and the database, which was the incident's gap.
Revisit if: traces turn out to be unused after two quarters of incidents; measure their use in postmortems first.

# ADR-008 — The HTTP service uses the standard library's WSGI support

Status: accepted
Date: 2026-11-25
Decided by: sam.o (architect of record)
Reviewed by: priya.n (engineering), aisha.r (security)
Links: ESC-N03, CON-1, CON-3, CON-4
Revisit when: Relay needs asynchronous request handling, generated API documentation, or a production server; any of these adds a dependency and needs its own ADR.

## Context

ADR-007 adds an HTTP service. Relay has no dependencies (`dependencies = []`), every lab runs offline, and
Chapter 13 will review every dependency as part of the supply chain. The service has four routes.

## Options considered

### Option A — Standard library: a WSGI application served by wsgiref in development

### Option B — A web framework, pinned in pyproject.toml

## Decision

Option A. `relay.service.app.RelayApp` is a plain WSGI callable, so any WSGI server can run it later without
changing the application. `python -m relay.service` serves it with `wsgiref.simple_server`, single-threaded and
bound to 127.0.0.1 by default.

## Consequences

- No new dependency, no new supply-chain review, and the labs stay offline.
- Routing, JSON handling and input validation are hand-written and tested (`tests/test_service_app.py`).
- `wsgiref` is not a production server. Chapter 11 runs the same application under one, which is a new
  dependency and a new ADR.

## Rejected alternatives

### Option B — A web framework, pinned in pyproject.toml
Rejected because: four routes do not repay a dependency that every lab would have to install and Chapter 13 would have to review, and the WSGI interface keeps the choice open.

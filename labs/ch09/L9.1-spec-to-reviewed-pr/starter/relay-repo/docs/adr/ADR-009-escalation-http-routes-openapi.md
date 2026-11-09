# ADR-009 — Escalation rule routes in relay.service, described by OpenAPI and validated on the server

Status: accepted
Date: 2026-12-01
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), lena.k (product)
Links: D2, D3, ESC-N03, ESC-N05, CON-1, CON-4
Revisit when: a second client needs routes the web client does not; or Relay adopts a framework that generates routes from OpenAPI (a dependency, so a new ADR under FF005); or rule deletion arrives with ESC-AC25's notices.

## Context

ESC-N03 requires rule permissions enforced on the server, and every change audited. Chapter 5's spec promised
that the service's rule routes would call `validate_rule` on the server, and that an OpenAPI description would
reference the JSON Schema contract. Relay 4.19.0 has neither. Spec ESC-SPEC-1 1.1.0 (behaviour B7) defines six
routes: list, read and replace rules; read a task's escalation panel; set a priority; acknowledge.

## Options considered

### Option A — Routes in relay.service, calling the engine's public interface; OpenAPI 3.1 file referencing the JSON Schema

### Option B — Validate in the route handlers only, with their own checks, and document the routes in prose

### Option C — Generate handlers and validation from the OpenAPI file with a framework

## Decision

Option A. A new module, `relay/service/escalation_routes.py`, handles the routes after RelayApp has authenticated
and rate limited the request. A rule change is checked twice on the server: against the JSON Schema contract, then
by `validate_rule`. The route contract is `specs/001-escalation-rules/contracts/escalation-api.openapi.json`, whose
bodies reference `escalation-rules.schema.json`. `tests/test_service_openapi.py` compares the description with the
service's route table, every refusal the tests observe, and every success body.

## Consequences

- One validator, one set of rules: the HTTP route and a library caller refuse a bad rule the same way.
- The service imports the engine only through `relay.escalation`, never its submodules. New fitness rule AR6 in
  `tests/test_architecture.py` enforces it, as AR2 does for the worker.
- Error bodies list failing field paths, never values, so an outside address in a refused rule is not echoed or
  audited.
- The OpenAPI file is hand-written. Drift between it and the code is caught by the contract test, not prevented.
- No delete route yet. ESC-AC25's notices to the Owner and Admins must arrive with it.

## Rejected alternatives

### Option B — Validate in the route handlers only, with their own checks, and document the routes in prose
Rejected because: two copies of the rules would drift apart, so the HTTP route and library callers could disagree about which rules are valid, and prose cannot be checked by a contract test.
Revisit if: the engine's validator becomes too slow to run on every request, which a load test would show (Chapter 17).

### Option C — Generate handlers and validation from the OpenAPI file with a framework
Rejected because: it adds a framework dependency that ADR-008 rejected for four routes, and six more routes do not change that balance for one team.
Revisit if: the service grows past about twenty routes, or a second team maintains routes; ADR-008's revisit condition names the same trigger.

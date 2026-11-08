# Relay release

| Measure | Value |
| --- | --- |
| Relay version | 4.20.0 |
| Spec | ESC-SPEC-1 1.1.0 |
| Criteria in the spec (of PRD v1.1's 31), full / partial | 23, 23 / 0 |
| Security constraints | 7 |
| Contract definitions; fields classified | 8; 42 of 42 |
| Tasks in the plan | 20 |
| Operations in the OpenAPI description | 6 |
| Test suite | 301 passed |
| Lint | lint: 0 problem(s) |
| Refusal-matrix cases (`test_SEC07_every_route_refuses`) | 32 |
| Oracle check on Relay's escalation and service tests: findings, blocking, exempt (properties, reviewed markers) | 5, 0, 5 (2, 3) |
| Files added since 4.19.0 | 20 |
| Files modified since 4.19.0 | 22 |

| Test file | Test cases |
| --- | ---: |
| `tests/escalation/test_escalation_acceptance.py` | 39 |
| `tests/escalation/test_escalation_contract.py` | 20 |
| `tests/escalation/test_escalation_delivery.py` | 7 |
| `tests/escalation/test_escalation_engine.py` | 28 |
| `tests/escalation/test_escalation_hours.py` | 18 |
| `tests/escalation/test_escalation_policy.py` | 6 |
| `tests/escalation/test_escalation_properties.py` | 8 |
| `tests/escalation/test_escalation_zones.py` | 3 |
| `tests/test_api.py` | 2 |
| `tests/test_architecture.py` | 10 |
| `tests/test_due_dates_rly412.py` | 15 |
| `tests/test_duedates.py` | 5 |
| `tests/test_roles.py` | 4 |
| `tests/test_service_app.py` | 24 |
| `tests/test_service_escalation.py` | 46 |
| `tests/test_service_http.py` | 2 |
| `tests/test_service_openapi.py` | 36 |
| `tests/test_store.py` | 3 |
| `tests/test_worker_queue.py` | 15 |
| `tests/test_worker_runner.py` | 10 |

Added:

- `docs/adr/ADR-009-escalation-http-routes-openapi.md`
- `docs/adr/ADR-010-business-hours-time-zones.md`
- `docs/adr/ADR-011-escalation-engine-storage-outbox.md`
- `specs/001-escalation-rules/contracts/escalation-api.openapi.json`
- `specs/001-escalation-rules/test-strategy.md`
- `src/relay/escalation/delivery.py`
- `src/relay/escalation/engine.py`
- `src/relay/escalation/hours.py`
- `src/relay/escalation/store.py`
- `src/relay/service/escalation_routes.py`
- `src/relay/service/responses.py`
- `tests/escalation/props.py`
- `tests/escalation/test_escalation_delivery.py`
- `tests/escalation/test_escalation_engine.py`
- `tests/escalation/test_escalation_hours.py`
- `tests/escalation/test_escalation_properties.py`
- `tests/escalation/test_escalation_zones.py`
- `tests/service_helpers.py`
- `tests/test_service_escalation.py`
- `tests/test_service_openapi.py`

Modified:

- `.github/CODEOWNERS`
- `AGENTS.md`
- `pyproject.toml`
- `specs/001-escalation-rules/contracts/escalation-rules.schema.json`
- `specs/001-escalation-rules/spec.md`
- `specs/001-escalation-rules/tasks.md`
- `src/relay/__init__.py`
- `src/relay/escalation/__init__.py`
- `src/relay/escalation/contract.py`
- `src/relay/escalation/evaluate.py`
- `src/relay/escalation/model.py`
- `src/relay/escalation/rules.py`
- `src/relay/service/__init__.py`
- `src/relay/service/__main__.py`
- `src/relay/service/app.py`
- `tests/escalation/escalation_fixtures.py`
- `tests/escalation/test_escalation_acceptance.py`
- `tests/escalation/test_escalation_contract.py`
- `tests/escalation/test_escalation_policy.py`
- `tests/test_architecture.py`
- `tests/test_service_app.py`
- `tests/test_service_http.py`

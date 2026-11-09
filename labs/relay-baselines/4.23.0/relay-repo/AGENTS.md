# Relay — instructions for coding agents

Read this file before changing anything. It is versioned with the code and
reviewed like code. If it is wrong, fix it in the same pull request.

## Project overview

Relay is a task and workflow platform. This repository is a teaching snapshot:
users and roles, projects and tasks, a SQLite task store, the JSON views the
web client renders, an HTTP service and a background triage worker (4.19.0), the escalation engine (4.20.0),
the OpenTofu configuration of its non-production AWS environment (4.21.0), and rule deletion, escalation
passes in the worker and the notification preferences module (4.22.0),
and agent identities, the audit trail of agent actions and the kill switch (4.23.0).
Python 3.11+, standard library only.

## Commands

- Test: `python -m pytest -q`
- Lint: `python tools/lint.py`
- Due-date check: `python tools/due_date_table.py --date 2026-11-20`
- Service (local only): `PYTHONPATH=src python -m relay.service --db relay.db --demo`
- Worker: `PYTHONPATH=src python -m relay.worker --db relay.db --drain` (add `--directory` and `--link-base`
  to run escalation passes too)

Run Test and Lint before you say a change is done. Paste their last lines into
the pull request description.

## Architecture

- `src/relay/models.py`: domain objects (User, Project, Task). Roles are Owner, Admin, Member, Guest.
- `src/relay/store.py`: the SQLite store. Due dates are stored as ISO calendar dates, never timestamps.
- `src/relay/timezones.py`: viewer time zones (a fixed offset table in this snapshot).
- `src/relay/duedates.py`: what date each viewer sees.
- `src/relay/roles.py`: permission rules. Only the Owner sees billing; Guests see invited projects only.
- `src/relay/api.py`: the views the client renders. It calls roles before returning data.
- `src/relay/service/`: the HTTP service (WSGI, standard library). It authenticates, rate limits and
  validates input, then calls the domain modules and the public interface of `relay.worker`.
- `src/relay/worker/`: the triage worker and its durable queue table. Triage is simulated here. The
  worker records suggestions only; it never changes a task. Each loop also runs the escalation pass (ADR-017).
- `src/relay/notify/`: notification preferences, modernized behind characterization tests (ADR-018). The legacy
  module is kept unchanged in `tests/notify/legacy_reference.py` as the tests' oracle; never edit it.
- `infra/`: OpenTofu for the non-production environment (ADR-012 to ADR-015); `infra/org/` holds the
  organization's guardrails. `deploy/`: the container images. Plan only: `tofu plan`, then the policy checks.
- Decisions: `docs/adr/`. `tests/test_architecture.py` enforces ADR-007's module boundaries.
- `src/relay/escalation/`: the escalation engine, built test-first from `specs/001-escalation-rules/`. It writes
  messages to an outbox and sends nothing (ADR-011); the service's rule routes call it (ADR-009).
- `src/relay/audit/`: agent identities and 15-minute tokens, the hash-chained audit trail, redaction and the
  kill switch (ADR-020 to ADR-023). `governance/agents.json` registers every agent; `infra/agents.tf` its roles.
- `specs/`: approved specifications. Change a spec in its own pull request before the code that follows it.

## Conventions

- Write the failing test first, in `tests/`, named after the ticket (for example `test_due_dates_rly412.py`).
- Name a test for an acceptance criterion after the criterion: `test_ESC_AC08_...` checks ESC-AC08.
- Expected values in tests come from the spec or a hand-worked example, never from running the code under test.
- One ticket per pull request: at most 200 changed lines outside `tests/` and 400 in all; split larger work.
- A schema change is a migration with a downgrade, and proves its copy before dropping anything (ADR-019).
- Approved tests are committed before the code; never change one in the commit that makes it pass.
- In a pull request description, list every claim about the code with the file and line that shows it.
- Stop and hand the task back to a person if the same test fails after three attempts, if you would change
  an approved test, if you need a file outside the task's list, or if you cannot show the line behind a claim.
- A due date is a calendar date. Do not convert it to or from an instant.
- Do not add dependencies. If you think one is needed, stop and say why.
- Never log a token, a request header or a request body. Pass anything bound for a log through `relay.audit.redact`.

## Boundaries

- Never read, print or copy secrets. There are none in this repository; if you find one, stop and report it.
- Do not edit `governance/`, `.github/` or this file's Boundaries section without a human request.
- Do not add a dependency, change a module boundary or edit `tests/test_architecture.py` without an
  accepted ADR in `docs/adr/` and a human request.
- Do not run commands that reach the network. For test data, use the local, read-only `relay-db-readonly` MCP tool.
- Never push to `main`, merge, or approve a pull request. A person reviews and merges every change.
- Never run `tofu apply`, `tofu destroy` or any command that changes a cloud account. A person applies a
  reviewed plan from the protected CI environment.
- You act under your own agent identity with 15-minute tokens. Never copy, print or store a token, never ask
  for a scope the task does not need, and never edit `governance/agents.json`, `infra/agents.tf` or `infra/detection/`.
- If a test fails for a reason you do not understand, stop and explain; do not delete or skip it.
- Do not change a test owned by `@relay/security`, a scanner or check configuration, or `.github/CODEOWNERS`;
  stop and ask the owner.

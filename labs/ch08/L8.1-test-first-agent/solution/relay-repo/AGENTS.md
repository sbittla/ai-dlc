# Relay — instructions for coding agents

Read this file before changing anything. It is versioned with the code and
reviewed like code. If it is wrong, fix it in the same pull request.

## Project overview

Relay is a task and workflow platform. This repository is a teaching snapshot:
users and roles, projects and tasks, a SQLite task store, the JSON views the
web client renders, an HTTP service and a background triage worker (4.19.0), and the escalation engine (4.20.0).
Python 3.11+, standard library only.

## Commands

- Test: `python -m pytest -q`
- Lint: `python tools/lint.py`
- Due-date check: `python tools/due_date_table.py --date 2026-11-20`
- Service (local only): `PYTHONPATH=src python -m relay.service --db relay.db --demo`
- Worker: `PYTHONPATH=src python -m relay.worker --db relay.db --drain`

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
  worker records suggestions only; it never changes a task.
- Decisions: `docs/adr/`. `tests/test_architecture.py` enforces ADR-007's module boundaries.
- `src/relay/escalation/`: the escalation engine, built test-first from `specs/001-escalation-rules/`. It writes
  messages to an outbox and sends nothing (ADR-011); the service's rule routes call it (ADR-009).
- `specs/`: approved specifications. Change a spec in its own pull request before the code that follows it.

## Conventions

- Write the failing test first, in `tests/`, named after the ticket (for example `test_due_dates_rly412.py`).
- Name a test for an acceptance criterion after the criterion: `test_ESC_AC08_...` checks ESC-AC08.
- Expected values in tests come from the spec or a hand-worked example, never from running the code under test.
- One ticket per pull request. Keep diffs under 200 changed lines; split larger work.
- A due date is a calendar date. Do not convert it to or from an instant.
- Do not add dependencies. If you think one is needed, stop and say why.

## Boundaries

- Never read, print or copy secrets. There are none in this repository; if you find one, stop and report it.
- Do not edit `governance/`, `.github/` or this file's Boundaries section without a human request.
- Do not add a dependency, change a module boundary or edit `tests/test_architecture.py` without an
  accepted ADR in `docs/adr/` and a human request.
- Do not run commands that reach the network. For test data, use the local, read-only `relay-db-readonly` MCP tool.
- Never push to `main`, merge, or approve a pull request. A person reviews and merges every change.
- If a test fails for a reason you do not understand, stop and explain; do not delete or skip it.

# ADR-007 — Relay service architecture

Status: proposed
Date: 2026-11-20
Decided by: relay-architect-agent
Links: D3, D10, ESC-N04, ESC-N11

## Context

Relay needs an HTTP service for escalation rules and a background process for ticket triage. The team wants the
architecture to be scalable, resilient and future-proof. Serverless functions were also mentioned.

## Options considered

### Option A — Modular monolith with an asynchronous triage worker

One application with a worker process and one database.

### Option B — Microservices

Separate services for tasks, escalation, triage and notification, communicating through a message broker. Each
service scales independently and each team can deploy on its own schedule.

## Decision

Option A, the modular monolith, because it is simpler for now.

## Rejected alternatives

### Option B — Microservices
Rejected because: too complex for now.

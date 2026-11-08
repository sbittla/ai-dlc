# ADR-009 — Use httpx for outbound HTTP from the service

Status: accepted
Date: 2026-12-01
Decided by: sam.o (architect of record)
Links: ESC-N09, CON-5
Dependency: httpx
Revisit when: the standard library's urllib meets the timeout and retry needs.

## Context

A seeded control case for Lab 6.2: a dependency that is declared and recorded.

## Options considered

### Option A — httpx, pinned

### Option B — urllib from the standard library

## Decision

Option A.

## Consequences

One new dependency, reviewed under Chapter 13's supply-chain rules.

## Rejected alternatives

### Option B — urllib from the standard library
Rejected because: it has no per-request connection pool or timeout split, which the webhook retries need.

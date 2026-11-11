# ADR-026 — Agent runs keep durable state, idempotent steps and approval gates

Status: accepted
Date: 2027-01-20
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: CON-1, CON-5, ADR-021, ADR-024, ADR-025
Revisit when: runs need to move between machines while running; or GitHub offers idempotency keys for creating pull requests; or an approval needs more than one approver. Review by 2028-01-20 in any case.

## Context

An agent's context lives in a model's prompt and is lost when its process stops. A run that crashes after opening a pull request, and is simply started again, opens a second one. A run that pauses for a person's approval must be able to wait for hours without holding a process. CON-5 already requires that Relay's webhook receivers be safe to receive twice; agent steps need the same property.

## Options considered

### Option A — A run store with a step journal, write-ahead intents and idempotency keys, plus approval gates bound to exact arguments

### Option B — Keep state in the model's context and restart failed runs from the beginning

### Option C — Approve the whole run up front instead of each high-impact call

## Decision

Option A. `relay.agents.state.RunStore` (SQLite, one `BEGIN IMMEDIATE` transaction per write) keeps runs, a step journal and checkpoints. Starting a run is idempotent by request key. Each non-read step has an idempotency key (Chapter 6's term, computed here by the runtime) built from its contract's fields, including derived ones such as a file's hash before an edit, and is recorded as `started` before its effect and `ok` or `error` after it; a repeated call with a key already `ok` returns the recorded result. A step found `started` on resume is run again only if its contract declares an idempotent handler (opening a pull request first looks for one on the run's branch); otherwise the run stops for a person (`unknown_outcome`). A step that ended in `error` is retried only if its handler is idempotent; otherwise the error is final for its key. `relay.agents.approval.ApprovalGate` records requests for gated calls and lets only an authenticated person decide: `decide` takes the person's own proof from the registry's person issuer, under five minutes old (Chapter 14). Under the `requester` rule only the person the run acts for may approve; under `another_person` only someone else may (raising a run's budget, which `apply_budget_raise` then stores in the run). Each approval is bound to the call's argument hash, including the diff's hash the boundary computes, and an undecided request expires after 24 hours. Requests and decisions go to the audit trail. `relay.agents.memory` compacts a context without ever dropping its pinned messages (the task, its constraints, the stop rules), and keeps long-term facts only with their source, run and agent; an agent may propose a fact, and only a person's review makes it retrievable.

## Consequences

- A crash, a budget stop, a kill switch or an approval pause leaves a run that another process can resume without repeating an external effect. Lab 10.2 drills each case.
- An approval covers one diff, computed from the branch, not reported by the agent. If the change differs, the requester is asked again (Lab 10.2's D08 and D13).
- The requester approves the diff, so the requester is not the pull request's independent reviewer: Chapter 9's PR10 counts an agent's commits as the person who ran it, and a code owner other than the requester must review.
- Delegation is authenticated per token exchange, and a person proof lasts five minutes. Budgets keep every run inside one 15-minute token, which is exchanged at the start with the trigger's proof; a run that waited for approval resumes only when its requester resumes it, with a fresh proof. A run that outlives its token without one stops as `delegation_expired`, not `revoked`: nothing was revoked, and its requester can resume it with a fresh proof (Lab 10.2's D16). After someone else approves a budget raise, it is likewise the requester who resumes the run.
- The audit trail alone shows whether every pull request was approved first; Lab 10.1 checks this on every held-out run.
- Waiting for approval costs no compute, and it is not counted in Lab 10.1's latency figures.
- The gate checks proofs that a verifier has already checked, as Relay's token exchange does (ADR-020); verifying the person issuer's signatures is part of the verifier Chapter 13 reviews.

## Rejected alternatives

### Option B — Keep state in the model's context and restart failed runs from the beginning
Rejected because: a restart repeats effects that already happened, and spends the budget again from zero.
Revisit if: never for runs with external effects.

### Option C — Approve the whole run up front instead of each high-impact call
Rejected because: a person would approve a change before it exists; the diff they approve must be the diff that is opened.
Revisit if: a task type moves to autonomy tier T4 under Chapter 19's bounded-autonomy rules.

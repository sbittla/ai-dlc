# ADR-039 — An incident assistant whose hypotheses must cite telemetry, and approval-gated remediation

Status: accepted
Date: 2027-02-10
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), tomas.b (support)
Links: D8, ESC-N09, CON-1
Related: ADR-022, ADR-026, ADR-036, ADR-038
Revisit when: the assistant's held-out evaluation set grows past 100 incidents; or it is asked to act rather than
propose. Review by 2027-08-10 in any case.
Supersedes: none.

## Context

On 2 February 2027 the incident assistant answered "what caused the latency?" with the 15:00 deploy, at high
stated confidence, citing only the deploy's time and the latency graph. The on-call engineer and the tech lead
approved a rollback on that basis. The rollback changed nothing, and the attack it hid continued for nearly two
hours. The assistant could not see security events; nothing asked it to show its evidence.

## Options considered

### Option A — Keep the assistant, require a citation for every claim, check the citations mechanically, and gate every action behind an authenticated person

### Option B — Remove the assistant from incident response

### Option C — Keep the assistant as it was and train people to be sceptical

## Decision

Option A.

- Each hypothesis cites telemetry: alert IDs, metric windows, span shares, events. One that names a cause and
  an effect is a cause hypothesis, whatever label the model gives it. The citation check resolves every
  citation, as of the moment of the claim, against a baseline the checker owns, and accepts a citation only if
  it is about the hypothesis's own cause, effect or the cause's mechanism. A cause needs a mechanism citation
  (the cause's component accounts for the effect), not only timing. The checker owns every threshold: the
  baseline, the minimum rise, a minimum mechanism share of one half, and evidence windows between the effect's
  onset and the moment of the check. A hypothesis with no citation is unsupported. A hypothesis is supported,
  unsupported or contradicted.
- The assistant reads reliability and security telemetry together.
- It proposes remediations; it never approves or runs them. Every request names the hypothesis it rests on.
  The gate runs the citation check on it itself and never takes a verdict from the caller. The hypothesis must
  be supported and must match the action: a rollback needs a cause that is the deploy being rolled back, a
  failover a database cause, a restart a worker cause, a sign-in limit an attribution citing SD-002 for only
  the networks SD-002 flagged, none wider than a /16 (IPv4) or /48 (IPv6). A claim
  with no structured cause and effect justifies nothing else. The gate refuses an agent's request that fails
  either test, and a person's unless the person gives an incident or ticket ID and a reason, which is audited. It authenticates requester and approvers with proofs under five
  minutes old, each bound to one request and used once; refuses agents as approvers and as kill-switch
  trippers; lets the requester of a two-person action be one of the two (on-call and tech lead), but never
  approve a one-person action; expires requests after 15 minutes; checks preconditions; and audits every
  refusal.
- Text found in telemetry is untrusted input to the assistant, never an instruction.
- The assistant is simulated in Lab 16.2. A registry entry `incident-assistant` is needed before a live
  assistant runs (`governance/agents.json`).

## Consequences

- An unsupported hypothesis can still be correct; the check says only that the evidence was not shown.
- The citation check and the gate are specified here and built in Lab 16.2, against simulated assistants and a
  lab person issuer. 4.27.0 does not ship either in `src/`: until the incident assistant has a registry entry and
  verifies proofs from the registry's `person_issuer`, people take every incident action through the runbooks, and
  an agent's proposals go through Chapter 10's approval gate. Moving both into Relay goes with the assistant's registry entry
  and the person issuer's verifier, in a later chapter.
- Every action is slower by one approval. Kill-switch trips stay open to any person and to DR-001 and DR-003.

## Rejected alternatives

### Option B — Remove the assistant from incident response
Rejected because: correlating a dozen signals across reliability and security telemetry is what people did badly on 2 February, and a checked assistant helps with exactly that.
Revisit if: two game days show that cited hypotheses do not shorten diagnosis.

### Option C — Keep the assistant as it was and train people to be sceptical
Rejected because: automation bias (Chapter 9) is strongest under time pressure, and an incident is the worst moment to rely on unaided scepticism.
Revisit if: never on its own; training complements the check.

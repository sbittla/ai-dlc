# ADR-NNN — <the decision, as a statement>

Status: proposed
Date: YYYY-MM-DD
Decided by: <a named person on the team, never an agent> (architect of record)
Reviewed by: <names and roles>
Links: <PRD decisions D1-D9, NFR IDs ESC-N01-N10 and constraints CON-1-CON-6 this decision serves>
Revisit when: <the observable change that would reopen this decision, and a review date>

<!--
Format rules the checker enforces (python -m archscore.report adr ...):
- The header fields above, before the first "##" heading. Status: proposed, accepted, superseded,
  deprecated or rejected. A superseded ADR also needs "Superseded by: ADR-NNN".
- Every option considered is a "### Option X — name" heading under "Options considered".
- The Decision section names the chosen option as "Option X".
- Every other option appears under "Rejected alternatives" with a line
  "Rejected because: <a reason of at least 8 words>". "Too complex" is not a reason; say what it would cost.
- At least one link to a PRD decision or NFR; every link must exist.
An agent may draft this file (tier T1). The person in "Decided by" approves it through a required review.
-->

## Context

What forces the decision: the drivers, with IDs, and the facts behind them (team, release process, load,
latency, cost). What is already decided elsewhere (link it).

## Options considered

### Option A — <name>

Structure in two or three sentences. Which drivers it serves well, and at what cost.

### Option B — <name>

## Decision

Option <X>. The evidence: scores and sensitivity from `archscore.report score`, structural counts, and anything
the scores cannot show.

## Consequences

What becomes easier, what becomes harder, the risks accepted (each with an owner), and the fitness functions
that will keep the code honest to this decision.

## Rejected alternatives

### Option B — <name>
Rejected because: <what it would cost, in terms of the drivers>.
Revisit if: <the change that would make it the better choice>.

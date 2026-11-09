# ADR-034 — Agent runs that read untrusted text: taint, approval for external effects, and trust carried through memory and compaction

Status: accepted
Date: 2027-02-09 (amended 2027-02-11: RECALL_MEMORY)
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: D3, ESC-N01, ESC-N03, CON-1
Related: ADR-024, ADR-025, ADR-026, ADR-032
Revisit when: an agent needs an external effect without approval after reading untrusted text, or a
plan-then-execute runtime replaces run-level taint. Review by 2027-08-09 in any case.
Supersedes: none.

## Context

The tool-call boundary (ADR-025) checks each call on its own. Chapter 3 named the lethal trifecta: private
data, untrusted content and a way out. A run that has read a ticket, an issue or a web page may now be
following the author's instructions, and each of its later calls can look ordinary on its own.

Chapter 12's red team also found two places where an instruction loses its origin. A summary written by
compaction (ADR-026) looks like the agent's own note, whatever it summarized. A memory proposed from a
ticket is reviewed once, by a person who sees a plausible fact, and is then recalled in every later run.

## Options considered

### Option A — Taint the run when it reads untrusted text; then refuse unapproved external effects, and carry trust through compaction and memory

### Option B — A plan-then-execute runtime: a planner that never sees untrusted text fixes the calls, and a quarantined model only extracts values

### Option C — Keep the boundary as it is and rely on approval gates already on external tools

## Decision

Option A. Option B is the direction for agents that need more than one external effect.

- A contract declares `untrusted_result` for tools whose results an outsider can write. After one such call
  succeeds, the run is tainted. The boundary reads the taint back from the run's journal when it is built,
  so a resumed run stays tainted.
- A tainted run's call to an external-effect tool with no approval rule is refused as `tainted_external`,
  and audited like every refusal. A gated external tool still waits for its approver; the audit record of
  the request says it came from a tainted run.
- A message carries `trust`. A compaction summary that replaces any untrusted message is untrusted,
  whatever the summarizer returned, and an untrusted message may not be pinned.
- Agents recall memory through `RECALL_MEMORY`, whose result is untrusted, so recall taints the run. This is
  persistence's second control, in a different module from the memory store: Lab 12.1's first coverage run
  found the pattern check and the review both in `relay.agents.memory`, so one bypass of the store defeated both.
- A memory fact proposed from an untrusted source is refused, and audited, if it holds an address, a link
  or an instruction to send, forward, copy or include something. Other untrusted facts may be proposed and
  reviewed, and recall returns their trust.

## Consequences

- An agent that reads a ticket and then wants to post a comment needs a person's approval for each comment.
  No Relay agent does that today.
- Taint is coarse: a run that read one harmless ticket is treated like one that read an attack. That is the
  intended bias.
- The memory rule is a pattern check, so a fact written to look harmless still passes it and still needs its
  reviewer. Lab 12.1's persistence cases measure that path.
- Option B is not built. It needs a planner with no access to untrusted text, which Relay's helper does not
  yet have.

## Rejected alternatives

### Option B — A plan-then-execute runtime: a planner that never sees untrusted text fixes the calls, and a quarantined model only extracts values
Rejected because: for now, Relay's helper has no planner that can work without reading the task's files, and building one is a larger change than the incident's fix needs.
Revisit if: an agent needs more than one external effect after reading untrusted text.

### Option C — Keep the boundary as it is and rely on approval gates already on external tools
Rejected because: an idempotent external tool may run without approval under ADR-025, and a reviewer who does not know the run read untrusted text cannot weigh the request.
Revisit if: every external tool in every contract is gated by a person.

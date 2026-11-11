# ADR-025 — Agents call tools only through typed contracts and one boundary, under their own identity

Status: accepted
Date: 2027-01-19
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: CON-1, ADR-020, ADR-021, Chapter 2 (Listing 2.4), Chapter 3 (scoped capabilities)
Revisit when: an agent needs a tool with an external effect other than opening a draft pull request; or Relay adopts an external policy engine; or internal tools move behind MCP servers with their own authorization. Review by 2028-01-19 in any case.

## Context

Chapter 2 sketched a tool-call boundary and Chapter 3 built one scoped tool. The incident's prototype gave its five agents one shared model API key and one GitHub token, plus a shell tool. Its provider bill could not say which agent spent what, and any agent could have pushed or commented wherever the token allowed.

## Options considered

### Option A — Typed contracts and a single boundary in `relay.agents`, one identity per agent

### Option B — A general shell tool inside the sandbox, constrained by instructions

### Option C — One service identity for the whole helper, shared by every agent in it

## Decision

Option A. A `ToolContract` declares each tool's typed parameters, its effect (read, write, external), the Relay scope it needs, who approves it, which arguments make two calls the same call, and how much of its result reaches the model. `ToolBoundary.call` checks, in order: the tool is in this agent's allowlist; the arguments satisfy the contract, including that a write touches only the task's files and never a test; the agent's own 15-minute token verifies for the scope, with no cache (ADR-020); the budget allows another step; arguments the model may not set (a diff's hash, a file's prior hash) are computed from the real state; a gated call has a person's approval of these exact arguments; and the journal does not already hold the call (ADR-026). Every call that reaches the boundary, refusals included, and including the refusals that end a run (revoked, budget), is written to the audit trail (ADR-021) with its arguments' hash, the agent's owner and its token's ID. Paths no agent may read are removed from any list of paths a tool returns. The helper's seven tools are in `relay.agents.tools`; none runs a shell, merges or approves.

## Consequences

- The kill switch (ADR-022) stops an agent on its next tool call, because every call verifies the token.
- Each agent in a multi-agent design needs its own registry entry, owner and scopes. That is a cost of the design, counted in ADR-027.
- The helper has its own GitHub App, `relay-spec-to-pr`, with the same permissions and limits as the coding sessions' `relay-agents`. A shared app would mean that tripping the helper's kill switch, which suspends its app's installation, also stopped every coding session.
- A task that needs a file outside its list cannot be done by the agent: the boundary refuses the edit, and the agent hands the task back (Chapter 9's stop signal).
- Tool results are cut to the contract's size before the model sees them, which bounds what one file or log can add to the context.

## Rejected alternatives

### Option B — A general shell tool inside the sandbox, constrained by instructions
Rejected because: instructions are advice to a model, not a control; a shell reaches the network, the token and every file the sandbox can see.
Revisit if: a task type needs commands no contract can express, and then only in a sandbox with no credentials.

### Option C — One service identity for the whole helper, shared by every agent in it
Rejected because: a shared identity cannot be attributed, scoped per role, or stopped for one agent without stopping all of them.
Revisit if: never; ADR-020 already forbids shared identities.

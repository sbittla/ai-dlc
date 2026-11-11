# ADR-050 — Agent-written code runs in a separate, locked-down process locally and in the sandbox task in the cloud

Status: accepted
Date: 2027-03-16
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N03, ESC-N07, CON-1
Related: ADR-012, ADR-013, ADR-025, ADR-034, ADR-035, ADR-049
Revisit when: the cloud sandbox runner is built; a microVM or user-space-kernel runtime is available to Relay's
tasks; or an agent needs network access beyond the egress proxy. Review by 2027-09-16 in any case.

## Context

The refund pilot ran the agent's code in a child process of the worker, in the worker's own container: with the
worker's environment (the payment provider's key), its filesystem and its network. Lab 18.1 ran nine of thirteen
escape attempts that way, and all nine reached what they tried: the key, a file beside the working directory,
the database file, an internal service on the loopback address, a shell, a process, native code, a write outside
the directory and a directory listing.

Relay's helper runs tests the agent wrote (`run_tests`, ADR-025), and any analysis agent that computes with code
needs the same tool. ADR-034 already treats repository files as untrusted, so code the agent writes after reading
them may be steered.

## Options considered

### Option A — A separate process with no environment, a throwaway directory, an audit-hook policy and limits; the separate sandbox task in the cloud

### Option B — Run the code in the worker's own process or container, as the pilot did

### Option C — A hosted code-execution service from a vendor

## Decision

Option A.

- `relay.agentops.sandbox.run_code` (local layer): a fresh interpreter in isolated mode, an empty environment, a
  throwaway working directory holding only the files passed in, reads elsewhere limited to the interpreter's own
  library, no network unless exact (host, port) pairs are allowed, a wall-clock timeout, an output cap, and on
  POSIX resource limits on CPU, memory, file size and open files. A PEP 578 audit hook refuses processes, the
  native-code paths it knows of (ctypes and cffi under any name, extension modules judged by their file, SQLite,
  Windows file APIs), every garbage-collector route to live objects, trace and profile functions, and traceback
  frames. `sys._getframe` and `f_back` stay allowed (the standard library needs them). The hook holds plain copies
  of the policy's values and of the builtins it calls, the module's globals are cleared before the agent runs, and
  it reads only exact str, bytes and int arguments. That stops the simpler attacks; it does not make the hook's
  state unreachable. Code in the same process can reach and change it (E21: a finalizer reaches the hook's own
  frame through a generator and rewrites a rule). The hook is a tripwire, not a boundary. Refusals go to the parent
  over a pipe the code cannot take back; the parent reads at most 64 KB of them and records a flood as `refused:report-overflow`.
- **The local layer is a policy check and a no-secrets environment, not a security boundary.** It runs only where
  nothing worth stealing is reachable: Chapter 3's dev container or an ephemeral CI runner with no credentials.
- **The cloud boundary is a sandbox runner of its own:** a task definition launched for one run and discarded,
  with no task role, a security group with no outbound rules (not even to the egress proxy), DNS resolution off,
  and its files passed in and its output and refusals passed back by the worker. A microVM or user-space-kernel
  runtime adds a kernel boundary where the platform offers one.
- **Not the existing sandbox task.** `relay-nonprod-sandbox` is Chapter 3's background-agent task: its proxy
  admits the code host and the package mirror, and its role may call the model. Code that got past the hook
  there would have an exfiltration channel and a spend path, so agent-written code never runs in it.
- The production `run_tests` contract declares `untrusted_result` (ADR-034), and `run_code` is the general tool.

## Consequences

- Lab 18.1: of 21 inert attempts, 16 were refused, 2 stopped by a limit and 1 found nothing; the legitimate
  attempt still works. Two were not stopped: learning whether a path exists outside the directory raises no audit
  event (E19), and code that reaches the hook's own frame rewrote its rules (E21). Six attempts (E14-E18, E20) got past earlier versions of this layer, through frames, rebound module
  globals and a changed class, the collector,
  an aliased C module and SQLite; the tests now keep each refused. Drill F5's steered code was refused and the run
  handed back without a pull request.
- SQLite is refused in the local sandbox, because it opens files below the hook's view (ATTACH, VACUUM INTO,
  extensions). Tests that need it wait for the cloud runner.
- On Windows the standard library offers no resource limits; there the timeout and the output cap are the only
  limits, and a memory test is skipped.
- The cloud sandbox runner is designed here and not built: until it is, agent code runs only in a credential-free
  dev container or CI runner, and not in the cloud. Owner sam.o, by 2027-05-31.
- Code that reaches native memory by a path the policy does not list gets past the hook; only the runner's task
  boundary, with no role and no route out, contains it.

## Rejected alternatives

### Option B — Run the code in the worker's own process or container, as the pilot did
Rejected because: the code then shares the worker's credentials, database and network, and the pilot's code reached all three in the lab.
Revisit if: never for agent-written code; trusted, reviewed code may run in the worker.

### Option C — A hosted code-execution service from a vendor
Rejected because: it sends Relay's code and test data to a new processor, needs a dependency and a data-protection review, and its isolation claims cannot be tested here.
Revisit if: the cloud sandbox runner cannot be built by 2027-05-31, after a DPIA and Chapter 13's review.

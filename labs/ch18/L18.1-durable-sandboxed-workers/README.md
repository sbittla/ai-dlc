# Lab 18.1 — Durable, Sandboxed Agent Workers with a Dead-Letter Queue, Workload Identity and Tracing

| | |
| --- | --- |
| Chapter | 18 — Running Agents in Production |
| Type | Core (all tracks) |
| Time | 5 hours |
| Cost ceiling | $0. Runs on your machine, offline: the model is a scripted stand-in, the code host and the payment provider are fakes, and the "internal service" is a listener on 127.0.0.1 |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

In the first week of March 2027 a refund assistant, piloted outside Relay's agent registry, refunded 16 charges
twice and ran the code it wrote with the worker's own environment and network. In this lab you replay that
pilot, then run Relay's spec-to-PR helper the way Chapter 18 runs agents in production: as a job on a durable
queue, under its own identity, with its code in a sandbox, its effects in a ledger, its failures in a
dead-letter state, and every attempt traced.

You have **Relay 4.30.0** in `relay-repo/`: canonical 4.28.0 plus `src/relay/agentops/` (the agent job queue,
the effect ledger, breakers, the sandbox, the registry's shared state and the service's agent gateway),
ADR-049 to ADR-052, and 104 new tests.

**About the data.** Everything in `data/` is **generated** by `scripts/generate_data.py` and **configured**,
not measured: the pilot's tickets and deliveries (a composite incident), the escape attempts and the drills
with their expected outcomes. The drills run Relay's real code on a **simulated clock**; the escape attempts
start real processes on your machine and are inert (each only tries to read, connect or start something).

## What you will practise

- Counting what **at-least-once delivery** does to an effect with no idempotency key, and which control removes
  which duplicate.
- Telling apart a **job**, a **run** and an **effect**, and keying each by the right thing.
- Running agent-written code in a **sandbox**, and saying honestly what a local process sandbox cannot stop.
- **Fault injection**: restart, duplicate, timeout, rate limit, sandbox escape, kill switch, cancellation and a
  poison message, each with its outcome written first.
- Reading one job **end to end** in a trace.

## Folder layout

```
L18.1-durable-sandboxed-workers/
├── relay-repo/                 ← Relay 4.30.0 (Chapter 18 branch): canonical 4.28.0 + relay.agentops; 992 tests
│   ├── src/relay/agentops/     ← jobs, effects, resilience, worker, sandbox, sandbox_child, tools, registry_state, gateway
│   └── docs/adr/               ← ADR-049 to ADR-052
├── data/                       ← GENERATED: pilot/tickets.jsonl, pilot/deliveries.jsonl, escapes.json, drills.json, manifest.json
├── scripts/generate_data.py
├── starter/opslab/
│   ├── replay.py               ← TODO 1: pilot_refunds; TODO 2: with_controls
│   ├── drills.py               ← TODO 3: verdict (the drills themselves are provided)
│   ├── escapes.py              ← TODO 4: classify
│   ├── traces.py               ← TODO 5: breakdown
│   ├── world.py                ← provided: the helper as a queue worker, in simulated time
│   └── report.py               ← provided
├── solution/opslab/            ← reference solution (instructors; read only after finishing)
├── templates/production-readiness-review.md
├── tests/                      ← test_opslab (hand-checkable), test_golden, test_relay
└── evidence/                   ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. To check the reference, in bash: `LAB_TARGET=solution python -m pytest -q`.
In PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. The variable persists
until it is removed, so always remove it, or later runs will silently grade the solution. Run pytest from this lab's
folder. Until you finish, failing tests stop with `NotImplementedError`; `tests/test_relay.py` passes from the start.

## Steps

### 1. Read the incident and the new package (20 min)

Read Chapter 18's opening incident, ADR-049 and ADR-050, and the docstrings of `relay-repo/src/relay/agentops/jobs.py`
and `effects.py`. Then run Relay's checks: `cd relay-repo && PYTHONPATH=src python -m pytest -q && python tools/lint.py`
(PowerShell: `$env:PYTHONPATH="src"; python -m pytest -q; Remove-Item Env:PYTHONPATH`). On Windows one POSIX-only
test is skipped (memory limits).

### 2. What the pilot did: TODO 1 (35 min)

Implement `pilot_refunds` in `replay.py`, then `cd starter && python -m opslab.report incident`. How many
deliveries were there for how many tickets, and why? Which cause made more duplicate refunds?

### 3. Which control removes which duplicate: TODO 2 (40 min)

Implement `with_controls`, then `python -m opslab.report layers > ../evidence/layers.md`. On Windows PowerShell 5.1,
`>` writes UTF-16; use `| Out-File -Encoding utf8 ../evidence/layers.md` instead. Dedup and heartbeats together
leave no duplicate here. Name a failure that would still produce one without the ledger. (Drill F1 is one.)

### 4. The sandbox: TODO 4 (45 min)

Implement `classify` in `escapes.py`, then `python -m opslab.report escapes`. Read `sandbox_child.decide`. Which
attempts does the pilot's way not even need an exploit for? Which refusals come from the audit hook, which from
the empty environment, and which from a limit? Write down two ways code could get past an audit hook, and what in
ADR-050 stops each in the cloud.

### 5. Drills: TODO 3 (50 min)

Implement `verdict` in `drills.py`, then `python -m opslab.report drills > ../evidence/drills.md`. For each drill,
say which control produced the outcome. Why does F3's run stay `running` when its job is dead? Why does F6's
refusal come 102 simulated seconds after the trip, and what in the runbook covers those seconds?

### 6. One job, end to end: TODO 5 (30 min)

Implement `breakdown` in `traces.py`, then `python -m opslab.report trace`. Where did the 724 seconds go? Which
span would you alert on, and which number belongs in an SLO?

### 7. Weaken one control (35 min)

Copy `relay-repo` to a scratch folder and make one change: pass `provider_idempotent=False` in
`agentops/tools.py`'s `ledgered_pull_request`; or remove the heartbeat call from `JobContext.checkpoint`; or run
`run_code(..., unrestricted=True)` in `sandboxed_tests`. Point `opslab` at the scratch copy (edit `RELAY_SRC` in
`starter/opslab/__init__.py`), rerun the drills and the escapes, and record which drill or attempt changed and how.
Undo the edit afterwards.

### 8. Shared registry state and the agent gateway (25 min)

Read ADR-051 and run `PYTHONPATH=src python -m pytest -q tests/test_agentops_registry_gateway.py -v` in `relay-repo`.
Explain why a 300-second verification cache would have broken drill F6, and what `relay.service.monitor` needs
before it trips a switch itself.

### 9. Production-readiness review (20 min)

Fill in `templates/production-readiness-review.md` for the helper as a queue worker. Then run the workspace audit from
`labs/ch03/L3.1-accountable-workspace/solution/`:
`python -m audit.report --policy ../data/policy.json --as-of 2027-03-19 --fail-on high ../../../ch18/L18.1-durable-sandboxed-workers/relay-repo`
(0 open, 0 waived).

## Expected evidence

- `evidence/layers.md` and `evidence/drills.md`, with a paragraph per drill naming the control that decided it.
- Your two audit-hook bypasses and the cloud control for each.
- The result of step 7.
- A completed `templates/production-readiness-review.md`.

## Troubleshooting

- `NotImplementedError: TODO n`: expected until you implement TODO n.
- A Windows firewall prompt during the escapes: the lab listens on 127.0.0.1 only; allow private networks or deny,
  the attempts still classify the same way.
- `PermissionError: [WinError 32]` when a drill cleans up: a database file was still open; the drills ignore it and
  leave a `lab18-*` folder in your temporary directory, which you may delete.
- Results differ from the chapter: check `LAB_TARGET`, then rerun `python scripts/generate_data.py` and
  `git diff data/`; the generated data must not change.
- `UnicodeEncodeError` on Windows: set `PYTHONIOENCODING=utf-8`.

## Known limits

**The local sandbox is a policy check and a no-secrets environment, not a security boundary.** It is an isolated
interpreter, an empty environment, a throwaway directory, an audit-hook policy and, on POSIX, resource limits. An audit
hook runs inside the process it watches: code that reaches native memory by a path the policy does not list gets past
it, and some actions raise no event at all (E19 learns which paths exist outside the directory). Six attempts in
`data/escapes.json` (E14 to E18, E20) got past earlier versions of it, and E21 gets past the current one: code in
the same process can reach and change the hook's own state. (On Python 3.12 and later E21 reaches its target, and
the report shows "contained 19 of 21". On 3.11, which CI uses, the collector happens to run E21's finalizer while
the hook is deciding, so the hook refuses it as reentrant: "contained 20 of 21". That is luck of timing, not a
defence; treat E21 as reached on every version.) The hook is a tripwire, not a boundary. Run agent code with it only in a credential-free
dev container or CI runner, never on a machine with your own credentials. The boundary in the cloud is ADR-050's
sandbox runner, its own task with no role and no outbound network; it is designed, not built (owner sam.o, by
2027-05-31). SQLite is refused inside the sandbox, because it opens files below the hook's view.

Also lab-only, and owned in ADR-049: the worker process (`opslab/world.py` builds it; nothing in Relay's `src/` does);
the person a job acts for (`World.build` manufactures that person's proof; the signed grant is designed, not built);
the approval route (the lab calls `decide_and_wake` directly); and the person-proof verifier. The model is scripted,
the clock is simulated, and SQLite stands in for the PostgreSQL adapter, which does not exist yet.

## Cleanup

The drills and the escapes delete their temporary folders. Delete `evidence/` contents you do not want to keep.

## Rubric (10 points)

| Points | Criterion |
| ---: | --- |
| 2 | Pilot replay and layer table correct (tests pass), with the failure that needs the ledger |
| 2 | Escape table correct, with two audit-hook bypasses and the cloud control for each |
| 3 | All drills pass, each explained by the control that produced it; F3 and F6 answered |
| 1 | Trace breakdown and the alert and SLO you would set |
| 2 | Weakened-control experiment and a complete production-readiness review |

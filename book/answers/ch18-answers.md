# Chapter 18 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch18/L18.1-durable-sandboxed-workers/` (its `relay-repo/` and `solution/opslab/`) and `labs/ch18/L18.2-inference-benchmark/solution/servelab/`. They are locked by each lab's `tests/test_answers.py` and `tests/test_golden.py`. The pilot's data, the drills' clock and the serving model are simulated and configured.

## Recall

**1. Three levels of keys.** Job: the kind and the business key, such as `spec-to-pr:RLY-2301`, in `agent_jobs`. Step: the run, the tool and the contract's fields, including derived ones, in `agent_steps` (Chapter 10). Effect: the business object the effect acts on, such as `refund:ch_05042` or `pr:RLY-2301`, in `agent_effects`, passed to the provider as its idempotency key.

Chapter 10's step keys include the run. Each of the pilot's duplicate deliveries would have started a new run, with a new run ID and so new step keys, and each run's refund would have been a first call under its own key. Only a key above the run, on the job or the effect, recognizes the second delivery as the same work. Full marks need all three keys and stores, and the reason the step key cannot help.

**2. Fencing tokens.** A lease says how long a worker may hold work; a fencing token says which claim a write belongs to. Every claim increases the token, and every heartbeat, completion or failure must carry it. A worker that was paused past its lease, and whose job someone else has claimed, is refused at its next write instead of overwriting the newer claim's work.

In F2 the second worker polled during the helper's 100-second test step. The first worker had extended its 120-second lease after the previous step, so the job was still leased and not available to claim. Full marks need the difference between the lease and the token, and the heartbeat as the reason in F2. Strong answers add that the heartbeat runs between steps, so a worker learns it lost the job before its next effect, not during one.

**3. Isolation layers.** From Table 18.3: a child process, an isolated process with a policy, a container, a user-space kernel, a microVM, and a separate account or project. In Relay's cloud environment the boundary is ADR-050's sandbox runner: a task of its own, launched per run, with no task role, no outbound network (not even the egress proxy) and DNS off. It is designed, not built, and until it exists agent code does not run in the cloud. Full marks also note that the existing sandbox task is not that boundary: its proxy reaches the code host and the mirror, and its role may call the model.

The audit hook is not the boundary because it runs inside the process it watches. Code that reaches native memory by a path the policy does not list, through a C extension or a bug, acts without the hook's consent, and some actions raise no event at all (E19). Earlier versions of Relay's hook were bypassed in pure Python (E14 to E18 and E20), and the current one still is (E21): code in the same process can reach and change the hook's own state. The hook is a tripwire that refuses and records careless or ordinary code in a credential-free environment; only the runner's task boundary contains what gets past it. Full marks need the list, the named boundary and the reason.

**4. Bandwidth and batching.** At the batch sizes most servers run, decode is limited by memory bandwidth: each step rereads every weight and the cache of every sequence to write one token per sequence. Prefill reads the prompt in one pass and is usually limited by arithmetic. In Table 18.9 the weights, 3 GB at 16 bits, are read once per step whatever the batch, about 10 ms at 300 GB/s plus 2 ms of overhead. Adding sequences adds only their cache reads: 64 sequences of 735 tokens add about 4.5 ms. So the step grows from 12.1 to 16.5 ms, 36% more, while the tokens written grow 64-fold. Full marks need the phase and the weight-versus-cache arithmetic.

## Apply

**5. Backoff.** (a) The ceilings are 15, 30, 60, 120, 240, 480 and 600 seconds; the seventh is capped. (b) Attempt 1 waits 0.20 × 15 = 3.0 s. Attempt 2's jittered delay, 0.55 × 30 = 16.5 s, is below the provider's Retry-After, so it waits 30 s. Attempt 3 waits 0.90 × 60 = 54.0 s. (c) Six attempts have five waits between them, each below its ceiling, so at most 15 + 30 + 60 + 120 + 240 = 465 s, unless a Retry-After lengthens one (Relay caps a Retry-After at an hour). Full marks need all three parts, with Retry-After as a floor in (b).

**6. Refunds by control.** With no controls every delivery refunds: 3 + 2 + 2 + 1 + 1 = 9 refunds, and the extra is A's two duplicates, B's one and C's one: 2 × $60 + $90 + $45 = $255. With deduplication only, B's webhook resend is the same job and starts no run, but the visibility-timeout deliveries are the same job handed to a second worker and do run: 8 refunds, $165 extra. With heartbeats only, the visibility-timeout deliveries never happen and B's resend is a new message: 6 refunds, $90 extra. With the ledger, every charge is refunded once: 5 refunds, $0. Lab 18.1's `tests/test_answers.py` replays this log through Relay's real queue and ledger. Full marks need all four rows and the reason deduplication does not stop a visibility-timeout redelivery.

**7. Tenfold volume.** Table 18.10's highest rates meeting the target are 2 requests a second for fp16 static, 16 for fp16 continuous and 32 for int4 continuous. At 5.3 requests a second with one spare: ceil(5.3 / 2) + 1 = 4 accelerators, ceil(5.3 / 16) + 1 = 2, and 2. At $0.80 an hour and 730 hours that is $2,336, $1,168 and $1,168 a month. The API costs 311,460 × $0.002183 = $679.92 a month, so self-hosting costs 3.4, 1.7 and 1.7 times as much.

Self-hosting is still dearer, and fp16 static is the worst choice because its tail fails early: it never breaks even, since one accelerator at full use costs $0.004969 a ticket against the API's $0.002183 (Table 18.11). Strong answers note what the comparison leaves out: engineering time, which favours the API at Relay's size; a quality evaluation, which no option has; and that the int4 option's speed comes with an unmeasured quality cost. Full marks need the three replica counts, the costs and the ratio.

## Design

**8. The cloud sandbox runner.** Marking notes; a strong answer covers:

- **Shape.** One task per code run is simplest to reason about, since nothing survives between runs, but costs start-up time per call. A warm pool of single-use tasks, each discarded after one run, keeps that property with less latency. A reused task must be reset, which is hard to prove.
- **Identity and role.** A task role with no permissions beyond what the code needs, which for tests is none: not even the model endpoint the existing sandbox task allows. No secrets in the environment or mounted volumes. The worker passes files in and receives output back through a path the worker controls, such as an object-store prefix per run with a short-lived, write-once grant, or the task's log stream.
- **Network.** The sandbox subnet with no route out, not even to the egress proxy, unless a contract allows an exact destination; the metadata endpoint blocked; DNS resolution off for the task.
- **Limits.** CPU, memory and ephemeral storage set on the task; a wall-clock timeout enforced by the worker, which stops the task; an output cap.
- **Results and refusals.** Exit status, a capped tail of the output and the policy's refusal log, recorded in the run's journal like a local run.
- **Testing containment.** The local escape catalogue run against the task, plus attempts that bypass the audit hook (native code, if the image includes a compiler or a library), checked by what the network and the role refuse. Then a check that the role's denies and the subnet's routes hold even when the code has a shell.
- **Kernel boundary.** A microVM or user-space-kernel runtime gives the code its own kernel, so a kernel exploit reaches a minimal guest rather than a shared host. Check the platform's documentation for the task type, and test with something observable from inside, such as the kernel version or the system calls the runtime does not implement.

Full marks need identity, network, limits, a containment test and an honest statement of what the platform does and does not guarantee.

**9. A safe refund assistant.** Marking notes; a strong answer covers:

- **Deterministic steps.** Finding the two charges and deciding whether they are a duplicate (same customer, same amount, same invoice line, within the card-retry window) is a query, not a model. Computing the refund amount is arithmetic.
- **The model's part, if any.** Reading the ticket to extract the charge reference when the customer did not give one, with the result validated against the payment records. If the deterministic rule cannot decide, the case goes to a person, not to the model.
- **Keys.** Job key `refund:<charge_id>`; effect key `refund:<charge_id>`, passed to the provider as its idempotency key; the run's request key from the job.
- **Code.** None should be needed. If the model writes any, it runs in the sandbox with no network and no environment.
- **Approval and cap.** Automatic only for exact duplicates under a cap, such as $400. Anything else needs a support person's approval of the exact amount and charge, authenticated as Chapter 10's gate requires, and a second person above a higher amount.
- **Identity.** A registered agent with one scope (refund duplicates under the cap), its own key with the provider, delegation from the support person who owns the queue, and its own kill switch.
- **Alerts.** Refund count and amount per hour against a baseline; any ledger conflict; any dead-letter job; reconciliation mismatches daily.
- **Drills.** A duplicate delivery, a redelivery while a run is slow, a crash after the provider refunded, a provider 429, a payload with a forged charge ID, a kill-switch trip, and a person cancelling.

Full marks need the deterministic core, the three keys, the cap and approval rule, and at least five drills.

# Lab 18.2 — Inference Benchmark on a Small Open-Weight Model

| | |
| --- | --- |
| Chapter | 18 — Running Agents in Production |
| Type | Stretch |
| Time | 3 hours |
| Cost ceiling | $0. The graded path is offline and simulated. The optional real run downloads about 271 MB once and runs on your CPU; nothing is billed |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). The optional real run needs its own virtual environment (step 7) |

## Brief

Chapter 2 promised that Chapter 18 would cover running models yourself. Relay calls a managed model API today
(ADR-052). In this lab you work out what self-hosting would take: how memory limits the requests in flight, why
decoding is limited by memory bandwidth, what continuous batching and quantization buy, and how many accelerators
Relay's triage peak would need, at what cost against the API.

**About the numbers.** The graded path uses a **simulated** serving model, `sim-open-1.5b` on `sim-accel-24`,
configured in `data/serving.json` and shaped like current open-weight models of about 1.5 billion parameters on a
24 GB inference accelerator. Neither is a real product. Its quality per precision is **configured**: it stands in for
the evaluation an intake would run. The accelerator's price is an **assumption** dated March 2027. Relay's volumes
come from Chapter 17's labs. `data/measured/smollm2-135m-author.json` is different: one **real** run of a small public
model on the author's laptop, recorded with `scripts/run_real_model.py`.

## What you will practise

- Computing weight memory, **KV cache** size and capacity for a model at three precisions.
- Estimating **prefill** and **decode** time from arithmetic and memory bandwidth.
- Comparing **static** and **continuous batching** on throughput, time to first token and the tail.
- Writing a **capacity plan** with a spare, and comparing it with a managed API's cost at Relay's volume.
- Taking a model file through an **intake**: pinned revision, safe format, hashes, licence, evaluation.

## Folder layout

```
L18.2-inference-benchmark/
├── data/
│   ├── serving.json, workload.json, relay-volume.json, model-manifest.json, manifest.json   ← GENERATED
│   └── measured/smollm2-135m-author.json   ← RECORDED once on the author's laptop (not generated)
├── scripts/generate_data.py
├── scripts/run_real_model.py   ← OPTIONAL real run; never run by the tests or CI
├── starter/servelab/
│   ├── model.py                ← TODO 1: memory; TODO 2: prefill and decode time
│   ├── engine.py               ← TODO 3: simulate (static and continuous batching)
│   ├── plan.py                 ← TODO 4a: capacity_plan; TODO 4b: break_even
│   └── report.py               ← provided
├── solution/servelab/          ← reference solution
├── templates/model-intake.md
├── tests/                      ← test_servelab (hand-checkable), test_golden, test_data
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. In bash: `LAB_TARGET=solution python -m pytest -q`. In PowerShell:
`$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Always remove the variable afterwards.
Until you finish, failing tests stop with `NotImplementedError`; `tests/test_data.py` passes from the start.

## Steps

### 1. Read (10 min)

Read Section 18.5 and `data/serving.json`. Which numbers are configured, which assumed, and which measured?

### 2. Memory: TODO 1 (25 min)

Implement the three memory functions in `model.py`, then `cd starter && python -m servelab.report memory`. Why does
quantizing the weights from 16 to 4 bits raise the KV capacity by only about 12%? What limits the batch here, memory or
`max_batch`?

### 3. Time: TODO 2 (20 min)

Implement `prefill_s` and `decode_step_s`. In the report's second table, why does a batch of 64 cost only 36% more per
step than a batch of 1?

### 4. Engines: TODO 3 (50 min)

Implement `simulate`, then `python -m servelab.report sweep > ../evidence/sweep.md` (PowerShell 5.1:
`| Out-File -Encoding utf8 ../evidence/sweep.md`). At what rate does each configuration stop meeting the SLO, and why
does static batching fail on time to first token at 8 requests a second while its throughput still rises?

### 5. Capacity plan: TODO 4 (25 min)

Implement `capacity_plan` and `break_even`, then `python -m servelab.report plan`. Why are all four options the same price today? Why does fp16 static never break even, however large the volume? What would
have to change for self-hosting to cost less than the API, and what does the comparison leave out?

### 6. Model intake (25 min)

Fill in `templates/model-intake.md` for the model in `data/model-manifest.json`. Why is `training_args.bin` on the
never-download list? What would the AI-BOM entry hold (Chapter 13)?

### 7. Optional: a real run (25 min)

Only if you want to measure; skip it and read `python -m servelab.report real` otherwise. In a separate environment:

```bash
python -m venv ../.venv
../.venv/Scripts/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0
../.venv/Scripts/python -m pip install -e ".[real]"
../.venv/Scripts/python scripts/run_real_model.py --out evidence/real-run.json
```

On Linux or macOS use `../.venv/bin/python`. Never install these into your global Python. The script downloads only the
files the manifest lists, at its revision, and refuses any whose hash differs. Compare your batch-to-sequential ratio
with the recorded one, not the absolute numbers.

## Expected evidence

- `evidence/sweep.md` with your answers to step 4.
- The capacity plan and a paragraph saying what would reopen ADR-052.
- A completed `templates/model-intake.md`.
- Optionally `evidence/real-run.json` and your comparison.

## Troubleshooting

- `NotImplementedError: TODO n`: expected until you implement TODO n.
- The real run fails to download: check your network; nothing else in the lab needs it.
- `refusing: ... does not match the manifest`: the file on the hub changed or the download was cut; delete
  `../.venv/models/` and retry. Never edit the manifest to make it pass.
- A pip resolver error for torch: install torch first from the CPU index, as shown, then the extra.

## Known limits

The serving model is a first-order model: memory bandwidth and arithmetic only, no scheduling overheads, no
preemption, no speculative decoding, no prefix caching. Its quality figures are placeholders. The real run is one model
far smaller than Relay would use, on one laptop CPU, once.

## Cleanup

Delete `labs/ch18/.venv/` to remove the optional environment and the downloaded model (about 1 GB in all with torch).

## Rubric (10 points)

| Points | Criterion |
| ---: | --- |
| 2 | Memory and timing correct (tests pass), with the bandwidth explanation |
| 3 | Engine simulation correct, with the SLO and throughput answers |
| 2 | Capacity plan, with what the cost comparison leaves out |
| 3 | A complete model intake, including the safe-format and hash checks |

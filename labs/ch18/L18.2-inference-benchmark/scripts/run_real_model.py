"""OPTIONAL: benchmark a real small open-weight model on your CPU. Never run by the tests or CI.

Cost: $0. It downloads about 271 MB once (the model's safetensors weights, 269 MB, plus its tokenizer and
configuration) and runs locally; nothing is sent anywhere else. Install into a separate virtual environment,
never your global Python (pinned versions, as tested on 2026-11-10):

    python -m venv ../.venv
    ../.venv/Scripts/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0
    ../.venv/Scripts/python -m pip install -e ".[real]"
    ../.venv/Scripts/python scripts/run_real_model.py --out evidence/real-run.json

(On Linux or macOS use ../.venv/bin/python. The CPU index keeps torch's download to about 200 MB on Windows;
the default index installs GPU libraries on Linux that are several GB.)

What it does, in order:
1. downloads ONLY the files listed in data/model-manifest.json, at the pinned revision, into ../.venv/models/;
2. refuses to continue if any file's size or SHA-256 differs from the manifest, or if any file other than the
   listed ones is present (a pickle such as training_args.bin is never fetched: loading one can run code);
3. loads the weights with `use_safetensors=True`;
4. runs five triage-shaped prompts one at a time, then the same five as one batch, greedy, at most 48 new
   tokens, and records time to first token, output rate and wall time, with the machine it ran on.

The model is far smaller than anything Relay would use for triage; the point is to measure, on real hardware,
the effects the simulation in servelab models: prefill versus decode, and what batching does to throughput.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import threading
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
PROMPTS = [
    "Ticket: I was charged twice for 3 seats this month. Please refund the second charge.",
    "Ticket: The export I started yesterday never finished and the button is greyed out.",
    "Ticket: How do I give a guest access to only one project?",
    "Ticket: Since this morning every webhook to our endpoint shows as degraded.",
    "Ticket: Our admin left the company; how do we transfer ownership of the workspace?",
]
SYSTEM = ("You triage support tickets for a task platform. Reply with JSON only: "
          '{"category": one of bug, feature_request, billing, access, how_to; "priority": P1 to P4}.')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(folder: Path, manifest: dict) -> None:
    present = {p.name for p in folder.iterdir() if p.is_file()}  # huggingface_hub's .cache/ is a folder
    extra = present - set(manifest["files"])
    if extra:
        raise SystemExit(f"refusing: files not in the manifest: {sorted(extra)}")
    for name, want in manifest["files"].items():
        path = folder / name
        if not path.exists():
            raise SystemExit(f"refusing: {name} is missing")
        if path.stat().st_size != want["bytes"] or sha256(path) != want["sha256"]:
            raise SystemExit(f"refusing: {name} does not match the manifest (size or SHA-256)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=str(LAB.parent / ".venv" / "models"))
    ap.add_argument("--out", default=str(LAB / "evidence" / "real-run.json"))
    ap.add_argument("--max-new-tokens", type=int, default=48)
    args = ap.parse_args()

    import torch
    import transformers
    from huggingface_hub import snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

    manifest = json.loads((LAB / "data" / "model-manifest.json").read_text(encoding="utf-8"))
    folder = Path(args.models) / manifest["model"].split("/")[-1]
    snapshot_download(manifest["model"], revision=manifest["revision"], allow_patterns=sorted(manifest["files"]),
                      local_dir=str(folder))
    verify(folder, manifest)

    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(str(folder))
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(str(folder), use_safetensors=True, dtype=torch.float32)
    model.eval()

    def chat(text: str) -> str:
        return tok.apply_chat_template([{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                                       tokenize=False, add_generation_prompt=True)

    single = []
    for text in PROMPTS:
        inputs = tok(chat(text), return_tensors="pt")
        streamer = TextIteratorStreamer(tok, skip_prompt=True)
        kwargs = dict(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False, streamer=streamer,
                      pad_token_id=tok.eos_token_id)
        start = time.perf_counter()
        thread = threading.Thread(target=model.generate, kwargs=kwargs)
        thread.start()
        first = None
        for piece in streamer:
            if first is None and piece:
                first = time.perf_counter() - start
        thread.join()
        wall = time.perf_counter() - start
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        new = int(out.shape[1] - inputs["input_ids"].shape[1])
        single.append({"input_tokens": int(inputs["input_ids"].shape[1]), "output_tokens": new,
                       "ttft_s": round(first or wall, 3), "wall_s": round(wall, 3)})

    batch_inputs = tok([chat(t) for t in PROMPTS], return_tensors="pt", padding=True)
    start = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**batch_inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    batch_wall = time.perf_counter() - start
    batch_tokens = int((out[:, batch_inputs["input_ids"].shape[1]:] != tok.pad_token_id).sum())

    result = {
        "model": manifest["model"], "revision": manifest["revision"], "verified_sha256": True,
        "environment": {"platform": platform.platform(), "cpus": os.cpu_count(), "python": platform.python_version(),
                        "torch": torch.__version__, "transformers": transformers.__version__, "threads":
                        torch.get_num_threads()},
        "settings": {"greedy": True, "max_new_tokens": args.max_new_tokens, "dtype": "float32"},
        "one_at_a_time": single,
        "summary": {
            "ttft_median_s": sorted(r["ttft_s"] for r in single)[len(single) // 2],
            "sequential_tokens_per_s": round(sum(r["output_tokens"] for r in single) /
                                             sum(r["wall_s"] for r in single), 1),
            "batch_of_5_wall_s": round(batch_wall, 3), "batch_of_5_tokens": batch_tokens,
            "batch_tokens_per_s": round(batch_tokens / batch_wall, 1),
        },
        "note": "measured once on the machine above; your numbers will differ. Not used by the tests.",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()

"""Lab 18.2's reports (provided). Run from starter/ or solution/:

    python -m servelab.report memory    # weights, KV cache and capacity per precision; a decode step by batch size
    python -m servelab.report sweep     # static and continuous batching, fp16 and int4, at five request rates
    python -m servelab.report plan      # self-hosting Relay's triage against the managed API
    python -m servelab.report real      # the optional real run's results, if evidence/real-run.json exists
    python -m servelab.report all

All numbers except `real` come from the SIMULATED serving model configured in data/serving.json.
"""

from __future__ import annotations

import json
import sys

from . import LAB_ROOT, load
from .engine import sweep
from .model import decode_step_s, kv_bytes_per_token, kv_capacity_tokens, weights_gb
from .plan import capacity_plan


def render_memory() -> str:
    serving = load("serving.json")
    model, accel = serving["model"], serving["accelerator"]
    rows = [f"Simulated: {model['name']} on {accel['name']} ({accel['memory_gb']:.0f} GB, "
            f"{accel['bandwidth_gb_s']:.0f} GB/s; {accel['usable_share']:.0%} usable)",
            "| Precision | Weights (GB) | KV cache per token (bytes) | KV capacity (tokens) | Configured quality |",
            "| --- | ---: | ---: | ---: | ---: |"]
    for name in ("fp16", "int8", "int4"):
        p = serving["precisions"][name]
        rows.append(f"| {name} | {weights_gb(model, p):.2f} | {kv_bytes_per_token(model, p):,} | "
                    f"{kv_capacity_tokens(model, accel, p):,} | {p['quality']:.1%} |")
    rows += ["", "| Batch (fp16, 735 tokens each) | Decode step (ms) | Tokens/s per sequence | Tokens/s in all |",
             "| ---: | ---: | ---: | ---: |"]
    fp16 = serving["precisions"]["fp16"]
    for batch in (1, 8, 32, 64):
        step = decode_step_s(batch * 735, model, accel, fp16)
        rows.append(f"| {batch} | {step * 1000:.1f} | {1 / step:.0f} | {batch / step:,.0f} |")
    return "\n".join(rows)


def render_sweep() -> str:
    slo = load("workload.json")["slo"]
    rows = [f"Simulated; 600 requests per row; SLO: TTFT p95 <= {slo['ttft_p95_s']:.1f} s and end-to-end p95 <= "
            f"{slo['e2e_p95_s']:.1f} s",
            "| Precision | Engine | Rate (req/s) | Output tokens/s | TTFT p50 (s) | TTFT p95 (s) | End-to-end p95 (s) "
            "| Meets SLO |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for s in sweep():
        rows.append(f"| {s.precision} | {s.engine} | {s.rate:g} | {s.tokens_per_s:,.1f} | {s.ttft_p50:.3f} | "
                    f"{s.ttft_p95:.3f} | {s.e2e_p95:.3f} | {'yes' if s.meets_slo else 'no'} |")
    return "\n".join(rows)


def render_plan() -> str:
    rows = sweep()
    accel = load("serving.json")["accelerator"]
    out = [f"Assumed accelerator price: ${accel['price_usd_per_hour']:.2f} an hour (as of {accel['price_as_of']}); "
           "managed API at Chapter 17's configuration A.",
           "| Option | Max rate meeting SLO (req/s) | Peak (req/s) | Utilization at peak | Replicas | "
           "Self-hosted $/month | API $/month | Ratio | Break-even tickets/month | Accelerators then |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for precision in ("fp16", "int4"):
        for engine in ("static", "continuous"):
            p = capacity_plan(rows, engine, precision)
            out.append(f"| {precision}, {engine} | {p.max_rate_meeting_slo:g} | {p.peak_rate:.3f} | "
                       f"{p.utilization_at_peak:.1%} | {p.replicas} | ${p.selfhost_usd_month:,.2f} | "
                       f"${p.api_usd_month:,.2f} | {p.ratio:.1f} | "
                       f"{'never' if p.break_even_tickets_month is None else f'{p.break_even_tickets_month:,}'} | "
                       f"{'-' if p.break_even_replicas is None else p.break_even_replicas} |")
    out.append("")
    for precision, engine in (("fp16", "static"), ("fp16", "continuous"), ("int4", "continuous")):
        q = capacity_plan(rows, engine, precision)
        out.append(f"{precision}, {engine}: one accelerator at full use costs ${q.usd_per_ticket_full_use:.6f} a ticket "
                   f"(API ${load('relay-volume.json')['api_usd_per_suggestion']:.6f}).")
    p = capacity_plan(rows, "continuous", "fp16")
    out.append(f"Relay's triage volume: {p.tickets_month:,} tickets a month; outage peak {p.peak_rate:.3f} requests a "
               f"second.")
    return "\n".join(out)


def render_real() -> str:
    """The real run recorded on the author's laptop (data/measured/), and yours if evidence/real-run.json exists."""
    out = []
    for label, path in (("Recorded (author's laptop)", LAB_ROOT / "data" / "measured" / "smollm2-135m-author.json"),
                        ("Yours", LAB_ROOT / "evidence" / "real-run.json")):
        if not path.exists():
            out.append(f"{label}: none (optional: scripts/run_real_model.py in labs/ch18/.venv).")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        s, env = d["summary"], d["environment"]
        out.append(f"{label}: {d['model']} at {d['revision'][:12]}, SHA-256 verified; {env['platform']}, "
                   f"{env['cpus']} logical CPUs, torch {env['torch']}, {d['settings']['dtype']}, greedy, at most "
                   f"{d['settings']['max_new_tokens']} new tokens.")
        out.append(f"  One at a time (5 prompts): median time to first token {s['ttft_median_s']:.3f} s, "
                   f"{s['sequential_tokens_per_s']:.1f} output tokens/s.")
        out.append(f"  The same 5 as one batch: {s['batch_of_5_tokens']} tokens in {s['batch_of_5_wall_s']:.3f} s, "
                   f"{s['batch_tokens_per_s']:.1f} tokens/s ({s['batch_tokens_per_s'] / s['sequential_tokens_per_s']:.1f}"
                   f" times the sequential rate).")
    return "\n".join(out)


RENDERERS = {"memory": render_memory, "sweep": render_sweep, "plan": render_plan, "real": render_real}


def main(argv: list[str]) -> int:
    which = argv[1] if len(argv) > 1 else "all"
    for name in (list(RENDERERS) if which == "all" else [which]):
        sys.stdout.write(RENDERERS[name]() + "\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

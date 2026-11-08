"""Run the evaluation and print a Markdown comparison.

Offline (default, free, deterministic):
    python -m harness.report --data ../data/tickets.jsonl --repeats 5

Live (costs money; needs `pip install anthropic` and credentials):
    python -m harness.report --data ../data/tickets.jsonl --repeats 3 --live claude-opus-5-5,claude-haiku-5-5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import models, prompt, runner


def render(summaries: list[runner.Summary], repeats: int) -> str:
    cols = [s.model for s in summaries]
    lines = [
        f"Prompt version: `{prompt.PROMPT_VERSION}` · repeats per ticket: {repeats}",
        "",
        "| Metric | " + " | ".join(cols) + " |",
        "| --- | " + " | ".join("---:" for _ in cols) + " |",
    ]

    def row(name, fn):
        lines.append(f"| {name} | " + " | ".join(fn(s) for s in summaries) + " |")

    row("Calls", lambda s: str(s.n))
    row("Fully correct", lambda s: f"{s.accuracy:.1%}")
    row("95% interval", lambda s: f"{s.accuracy_ci[0]:.1%} – {s.accuracy_ci[1]:.1%}")
    row("Correct, easy tickets", lambda s: f"{s.accuracy_easy:.1%}")
    row("Correct, hard tickets", lambda s: f"{s.accuracy_hard:.1%}")
    for f in ("category", "priority", "team"):
        row(f"Field accuracy: {f}", lambda s, f=f: f"{s.field_accuracy[f]:.1%}")
    row("Schema-valid outputs", lambda s: f"{s.schema_valid:.1%}")
    row("Failures by kind", lambda s: ", ".join(f"{k} {v}" for k, v in sorted(s.errors.items())) or "none")
    row("Consistent across repeats", lambda s: f"{s.consistency:.1%}")
    row("Followed injected instruction (TK32)", lambda s: f"{s.injection_obeyed:.0%}")
    row("Latency p50 (s)", lambda s: f"{s.latency_p50_s:.2f}")
    row("Latency p95 (s)", lambda s: f"{s.latency_p95_s:.2f}")
    row("Cost per call (USD)", lambda s: f"{s.cost_per_call_usd:.6f}")
    row("Cost per correct answer (USD)", lambda s: f"{s.cost_per_correct_usd:.6f}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Relay triage model evaluation")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--live", help="comma-separated Claude model IDs (costs money)")
    ap.add_argument("--tokens", action="store_true", help="also print the token budget of one request")
    ap.add_argument("--by-ticket", action="store_true", help="also print intervals that resample tickets, not calls")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page

    tickets = runner.load_tickets(args.data)
    if args.live:
        clients = [models.live_model(m.strip()) for m in args.live.split(",")]
    else:
        gold = {t["id"]: t for t in tickets}
        sims = models.simulated_models(gold)
        clients = [sims["sim-large"], sims["sim-small"]]
    records = runner.run_eval(clients, tickets, args.repeats)
    print(render(runner.summarise(records), args.repeats))
    if args.tokens:
        tb = runner.token_budget(tickets, records)
        print(f"\nToken budget (estimated): system prompt {tb.system_tokens}, ticket mean {tb.ticket_tokens_mean:.1f} "
              f"(max {tb.ticket_tokens_max}), output mean {tb.output_tokens_mean:.1f}; "
              f"system prompt share of input {tb.system_share:.1%}")
    if args.by_ticket and len(clients) == 2:
        ci = runner.ticket_bootstrap(records, clients[0].name, clients[1].name)
        print(f"\nTicket-level 95% intervals: {clients[0].name} {ci['a'][0]:.1%} – {ci['a'][1]:.1%}; "
              f"{clients[1].name} {ci['b'][0]:.1%} – {ci['b'][1]:.1%}; "
              f"difference {ci['difference'][0] * 100:+.1f} to {ci['difference'][1] * 100:+.1f} points")


if __name__ == "__main__":
    main()

"""Compare context strategies on Relay's documentation questions.

Offline (default, free): measures whether the answer reaches the model and
how many tokens each strategy costs.

    python -m ctx.report --data ../data

Live (optional, costs money): also asks a Claude model each question under
each strategy and checks whether its answer contains the expected phrase.

    python -m ctx.report --data ../data --live claude-haiku-5-5

Live runs are capped by --max-usd (default $1.00): a call is refused before it is made if its
worst-case cost (pessimistic input estimate, every output token up to max_tokens) would take spend
past the ceiling.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from . import retrieval, strategies

LIVE_PRICES = {  # USD per million tokens (input, output); list prices, verify before use
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
# The offline table prices context at a large model's input price, the expensive case for "full".
CONTEXT_COST_MODEL = "claude-opus-5-5"
LIVE_MAX_TOKENS = 512
CHARS_PER_TOKEN_PESSIMISTIC = 2  # real tokenizers average 3-4 characters per token; assume fewer


def call_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = LIVE_PRICES[model]
    return input_tokens / 1_000_000 * p_in + output_tokens / 1_000_000 * p_out


def worst_case_call_usd(model: str, prompt: str, max_tokens: int = LIVE_MAX_TOKENS) -> float:
    """The most one call can cost: input at one token per 2 characters, and every output token billed."""
    return call_usd(model, math.ceil(len(prompt) / CHARS_PER_TOKEN_PESSIMISTIC), max_tokens)


def run(data: Path, k_values=(1, 3, 5), kind: str | None = None) -> list[tuple[str, strategies.StrategyResult]]:
    """Evaluate every strategy; `kind` restricts to "keyword" or "paraphrase" questions."""
    docs = retrieval.load_docs(data / "docs")
    questions = [q for q in retrieval.load_questions(data / "questions.jsonl") if kind is None or q["type"] == kind]
    rows = [("none", strategies.evaluate("none", questions, docs, None)),
            ("full", strategies.evaluate("full", questions, docs, None))]
    for with_title in (False, True):
        chunks = [c for name, text in docs.items() for c in retrieval.chunk_document(name, text, with_title)]
        index = retrieval.BM25(chunks)
        label = "titled chunks" if with_title else "plain chunks"
        for k in k_values:
            rows.append((f"BM25 top-{k}, {label}", strategies.evaluate("bm25", questions, docs, index, k)))
    synonyms = retrieval.load_synonyms(data / "synonyms.json")
    for k in k_values:
        rows.append((f"BM25 top-{k}, titled chunks, expanded query",
                     strategies.evaluate("bm25", questions, docs, index, k, synonyms)))
    return rows


def render(rows) -> str:
    lines = ["| Strategy | Answer reaches the model | Mean context tokens | Max context tokens | MRR@k | Context cost per 1,000 questions (USD) |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, r in rows:
        mrr = f"{r.mrr_at_k:.2f}" if r.mrr_at_k is not None else "—"
        cost = r.mean_tokens * 1000 / 1_000_000 * LIVE_PRICES[CONTEXT_COST_MODEL][0]
        lines.append(f"| {label} | {r.answer_in_context:.0%} | {r.mean_tokens:.0f} | {r.max_tokens} | {mrr} | {cost:.2f} |")
    return "\n".join(lines)


def live(data: Path, model: str, k: int = 3, max_usd: float = 1.00, client=None) -> str:
    """Ask a real model each question under each strategy. Costs money; needs the `live` extra.

    Uses titled chunks for the bm25 strategy. Refusals, truncation, API errors and
    calls stopped by the spend ceiling are counted separately rather than ending the run.
    """
    if model not in LIVE_PRICES:
        raise ValueError(f"add a price for {model} to LIVE_PRICES first")
    import anthropic

    client = client or anthropic.Anthropic()
    spent = 0.0
    docs = retrieval.load_docs(data / "docs")
    questions = retrieval.load_questions(data / "questions.jsonl")
    chunks = [c for name, text in docs.items() for c in retrieval.chunk_document(name, text)]
    index = retrieval.BM25(chunks)
    lines = ["| Strategy (bm25 = titled chunks, top-3) | Answers containing the expected phrase "
             "| Refused / truncated / errors / stopped by budget | Input tokens (total) | Output tokens (total) | Cost (USD) |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for strategy in ("none", "full", "bm25"):
        correct, tokens, out_tokens, cost, refused, truncated, errors, stopped = 0, 0, 0, 0.0, 0, 0, 0, 0
        for q in questions:
            ctx = strategies.build_context(strategy, q["question"], docs, index, k)
            prompt = strategies.QUESTION_TEMPLATE.format(context=ctx.text or "(no context)", question=q["question"])
            if spent + worst_case_call_usd(model, prompt) > max_usd:
                stopped += 1  # checked before the call, so spend never passes the ceiling
                continue
            try:
                resp = client.messages.create(model=model, max_tokens=LIVE_MAX_TOKENS, output_config={"effort": "low"},
                                              messages=[{"role": "user", "content": prompt}])
            except anthropic.APIError:
                errors += 1
                continue
            usd = call_usd(model, resp.usage.input_tokens, resp.usage.output_tokens)
            spent += usd
            cost += usd
            tokens += resp.usage.input_tokens
            out_tokens += resp.usage.output_tokens
            if resp.stop_reason == "refusal":
                refused += 1
                continue
            if resp.stop_reason == "max_tokens":
                truncated += 1
            text = "".join(b.text for b in resp.content if b.type == "text")
            correct += q["answer"].lower() in text.lower()
        lines.append(f"| {strategy} | {correct}/{len(questions)} | {refused} / {truncated} / {errors} / {stopped} "
                     f"| {tokens:,} | {out_tokens:,} | {cost:.4f} |")
    lines.append(f"\nLive spend ${spent:.4f} of ceiling ${max_usd:.2f} ({model} at ${LIVE_PRICES[model][0]:.2f} / "
                 f"${LIVE_PRICES[model][1]:.2f} per million input / output tokens)")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare context strategies")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--live", help="a Claude model ID; costs money")
    ap.add_argument("--max-usd", type=float, default=1.00, help="live-mode spend ceiling (default $1.00)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    titles = {"keyword": "Keyword questions (reuse the docs' words)",
              "paraphrase": "Paraphrased questions (synonym map was tuned on these)",
              "heldout": "Held-out paraphrased questions (never used for tuning)"}
    for kind in ("keyword", "paraphrase", "heldout"):
        print(f"### {titles[kind]}\n")
        print(render(run(args.data, kind=kind)))
        print()
    if args.live:
        print()
        print(live(args.data, args.live, max_usd=args.max_usd))


if __name__ == "__main__":
    main()

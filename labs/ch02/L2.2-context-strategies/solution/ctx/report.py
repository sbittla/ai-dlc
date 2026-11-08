"""Compare context strategies on Relay's documentation questions.

Offline (default, free): measures whether the answer reaches the model and
how many tokens each strategy costs.

    python -m ctx.report --data ../data

Live (optional, costs money): also asks a Claude model each question under
each strategy and checks whether its answer contains the expected phrase.

    python -m ctx.report --data ../data --live claude-haiku-5-5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import retrieval, strategies

PRICE_IN_PER_MTOK = 4.00  # USD per million input tokens; an assumption, check current prices


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
        cost = r.mean_tokens * 1000 / 1_000_000 * PRICE_IN_PER_MTOK
        lines.append(f"| {label} | {r.answer_in_context:.0%} | {r.mean_tokens:.0f} | {r.max_tokens} | {mrr} | {cost:.2f} |")
    return "\n".join(lines)


def live(data: Path, model: str, k: int = 3) -> str:
    """Ask a real model each question under each strategy. Costs money; needs the `live` extra.

    Uses titled chunks for the bm25 strategy. Refusals, truncation and API
    errors are counted separately rather than ending the run.
    """
    import anthropic

    client = anthropic.Anthropic()
    docs = retrieval.load_docs(data / "docs")
    questions = retrieval.load_questions(data / "questions.jsonl")
    chunks = [c for name, text in docs.items() for c in retrieval.chunk_document(name, text)]
    index = retrieval.BM25(chunks)
    lines = ["| Strategy (bm25 = titled chunks, top-3) | Answers containing the expected phrase | Refused / truncated / errors | Input tokens (total) |",
             "| --- | ---: | ---: | ---: |"]
    for strategy in ("none", "full", "bm25"):
        correct, tokens, refused, truncated, errors = 0, 0, 0, 0, 0
        for q in questions:
            ctx = strategies.build_context(strategy, q["question"], docs, index, k)
            prompt = strategies.QUESTION_TEMPLATE.format(context=ctx.text or "(no context)", question=q["question"])
            try:
                resp = client.messages.create(model=model, max_tokens=512, output_config={"effort": "low"},
                                              messages=[{"role": "user", "content": prompt}])
            except anthropic.APIError:
                errors += 1
                continue
            tokens += resp.usage.input_tokens
            if resp.stop_reason == "refusal":
                refused += 1
                continue
            if resp.stop_reason == "max_tokens":
                truncated += 1
            text = "".join(b.text for b in resp.content if b.type == "text")
            correct += q["answer"].lower() in text.lower()
        lines.append(f"| {strategy} | {correct}/{len(questions)} | {refused} / {truncated} / {errors} | {tokens:,} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare context strategies")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--live", help="a Claude model ID; costs money")
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
        print(live(args.data, args.live))


if __name__ == "__main__":
    main()

"""Explain one retrieval result: the tokens, the overlap and the ranking.

    python -m ctx.explain --data ../data --question P05

Retrieval failures are silent in the final answer. This tool makes one of
them visible, as in Chapter 2's "Anatomy of a miss".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import retrieval


def explain(data: Path, qid: str, with_title: bool = True, show: int = 4) -> str:
    docs = retrieval.load_docs(data / "docs")
    q = {x["id"]: x for x in retrieval.load_questions(data / "questions.jsonl")}[qid]
    chunks = [c for name, text in docs.items() for c in retrieval.chunk_document(name, text, with_title)]
    index = retrieval.BM25(chunks)
    q_tokens = retrieval.tokenize(q["question"])
    ranked = index.search(q["question"], len(chunks))
    answer_chunks = [c for c in chunks if c.doc == q["source"] and q["answer"].lower() in c.text.lower()]
    lines = [
        f"Question {qid}: {q['question']}",
        f"Query tokens ({len(q_tokens)}): {', '.join(q_tokens)}",
        f"Chunks indexed: {len(chunks)}",
    ]
    for ac in answer_chunks:
        shared = sorted(set(q_tokens) & set(retrieval.tokenize(ac.text)))
        rank = next((i for i, (c, _) in enumerate(ranked, 1) if c.chunk_id == ac.chunk_id), None)
        lines.append(f"Answer chunk {ac.chunk_id}: shares {len(shared)} token(s) {shared}; rank {rank or 'not retrieved'}")
    lines.append(f"Top {show}:")
    for i, (c, score) in enumerate(ranked[:show], 1):
        lines.append(f"  {i}. {c.chunk_id} (score {score:.2f})")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Explain one retrieval result")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--question", required=True, help="question id, e.g. P05")
    ap.add_argument("--plain", action="store_true", help="index chunks without title headers")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(explain(args.data, args.question, with_title=not args.plain))


if __name__ == "__main__":
    main()

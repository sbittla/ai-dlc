"""Build the context an LLM would see under each strategy, and measure it (STARTER: implement the TODO functions)."""

from __future__ import annotations

from dataclasses import dataclass

from .retrieval import BM25, Chunk, estimate_tokens, expand_query

QUESTION_TEMPLATE = "Answer using only the context. If the context does not contain the answer, say so.\n\n{context}\n\nQuestion: {question}"


@dataclass(frozen=True)
class Context:
    strategy: str
    passages: tuple[tuple[str, str], ...]  # (source document, text), in the order the model sees them

    @property
    def text(self) -> str:
        return "\n\n".join(text for _, text in self.passages)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def build_context(strategy: str, question: str, docs: dict[str, str], index: BM25 | None, k: int = 3,
                  synonyms: dict[str, list[str]] | None = None) -> Context:
    """Context under one strategy.

    none : no context at all (the model must rely on what it already knows)
    full : every document, in file-name order
    bm25 : the top-k chunks from `index` for the question, best first;
           if `synonyms` is given, the query is expanded first
    """
    if strategy == "none":
        return Context("none", ())
    if strategy == "full":
        return Context("full", tuple((name, docs[name]) for name in sorted(docs)))
    if strategy == "bm25":
        if index is None:
            raise ValueError("bm25 strategy needs an index")
        query = expand_query(question, synonyms) if synonyms else question
        return Context(f"bm25-k{k}", tuple((c.doc, c.text) for c, _ in index.search(query, k)))
    raise ValueError(f"unknown strategy {strategy!r}")


def answer_in_context(answer: str, source: str, context: Context) -> bool:
    """True when a passage from the `source` document contains the answer phrase (case-insensitive).

    Requiring the source document avoids false hits: "15 minutes" appears in
    more than one Relay document. This measures whether the model *could*
    answer from the context, an upper bound on what retrieval allows.
    """
    # TODO(L2.2): implement using the definition in the docstring.
    raise NotImplementedError("answer_in_context")


def reciprocal_rank(answer: str, source: str, ranked: list[Chunk]) -> float:
    """1 / rank of the first chunk from `source` containing the answer phrase (rank from 1); 0 if none.

    Computed over the ranked list it is given, so over top-k results this is
    reciprocal rank at k: a chunk ranked below k counts as 0.
    """
    # TODO(L2.2): implement using the definition in the docstring.
    raise NotImplementedError("reciprocal_rank")


@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    answer_in_context: float  # share of questions
    mean_tokens: float
    max_tokens: int
    mrr_at_k: float | None    # mean reciprocal rank at k, retrieval strategies only


def evaluate(strategy: str, questions: list[dict], docs: dict[str, str], index: BM25 | None, k: int = 3,
             synonyms: dict[str, list[str]] | None = None) -> StrategyResult:
    contexts = [build_context(strategy, q["question"], docs, index, k, synonyms) for q in questions]
    hit = [answer_in_context(q["answer"], q["source"], c) for q, c in zip(questions, contexts)]
    mrr = None
    if strategy == "bm25":
        def query(q):
            return expand_query(q["question"], synonyms) if synonyms else q["question"]
        rr = [reciprocal_rank(q["answer"], q["source"], [c for c, _ in index.search(query(q), k)]) for q in questions]
        mrr = sum(rr) / len(rr)
    toks = [c.tokens for c in contexts]
    return StrategyResult(contexts[0].strategy, sum(hit) / len(hit), sum(toks) / len(toks), max(toks), mrr)

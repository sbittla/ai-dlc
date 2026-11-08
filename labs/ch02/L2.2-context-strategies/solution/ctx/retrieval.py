"""Chunking, tokenizing and BM25 retrieval over Relay's docs (reference solution).

BM25 is a decades-old keyword ranking function. It is used here because it
is small enough to implement and inspect in an afternoon, runs offline, and
is still a strong baseline that production retrieval systems are compared
against. Embedding-based retrieval is discussed in the chapter.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how in is it its of on or "
    "the to what when which who whose why will with within after".split()
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str   # "<doc>#<n>", n counted from 1
    doc: str        # source file name
    text: str


def load_docs(folder: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md"))}


def load_questions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def estimate_tokens(text: str) -> int:
    """Rough token estimate: one token per four characters, rounded up.

    Real tokenizers differ by model and language; use the provider's token
    counting endpoint when cost matters. This estimate is good enough to
    compare strategies with each other.
    """
    return math.ceil(len(text) / 4)


def tokenize(text: str) -> list[str]:
    """Lower-case word tokens for retrieval: runs of letters and digits, stopwords removed.

    "X-Relay-Signature header" -> ["x", "relay", "signature", "header"]
    """
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def chunk_document(doc: str, text: str, with_title: bool = True) -> list[Chunk]:
    """Split a Markdown document into one chunk per paragraph.

    Paragraphs are separated by blank lines. The '# Title' line is not a chunk
    of its own. When `with_title` is True, the title is prefixed to every
    chunk ("Title: <title>\\n<paragraph>"), so a paragraph that never repeats
    its subject (for example "Failed deliveries are retried 8 times") can
    still be found by a query about webhooks.
    """
    title = ""
    paragraphs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            title = block[2:].strip()
            continue
        paragraphs.append(block)
    chunks = []
    for i, para in enumerate(paragraphs, start=1):
        body = f"Title: {title}\n{para}" if with_title and title else para
        chunks.append(Chunk(f"{doc}#{i}", doc, body))
    return chunks


def load_synonyms(path: Path) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_query(query: str, synonyms: dict[str, list[str]]) -> str:
    """Append the synonyms of every query token to the query.

    "How do I check it?" with {"check": ["verify"]} -> "How do I check it? verify".
    Original words stay, so expansion can only add matches, never remove them.
    Synonyms are appended once each, in the order first seen.
    """
    extra: list[str] = []
    for token in tokenize(query):
        for word in synonyms.get(token, []):
            if word not in extra:
                extra.append(word)
    return f"{query} {' '.join(extra)}" if extra else query


class BM25:
    """Okapi BM25 ranking over a fixed list of chunks.

    score(q, d) = sum over query terms t of
        idf(t) * tf(t, d) * (k1 + 1) / (tf(t, d) + k1 * (1 - b + b * len(d) / avgdl))
    with idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5)).

    tf counts occurrences of t in the chunk's tokens; len(d) is the chunk's
    token count; avgdl is the mean token count over all chunks; N is the
    number of chunks; df(t) is the number of chunks containing t. Repeated
    query terms count once.
    """

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        if not chunks:
            raise ValueError("no chunks to index")
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.tokens = [tokenize(c.text) for c in chunks]
        self.tf = [Counter(t) for t in self.tokens]
        self.avgdl = sum(len(t) for t in self.tokens) / len(self.tokens)
        df: Counter = Counter()
        for toks in self.tokens:
            df.update(set(toks))
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str, i: int) -> float:
        """BM25 score of chunk i for `query`, using the formula in the class docstring."""
        tf, dl = self.tf[i], len(self.tokens[i])
        total = 0.0
        for term in set(tokenize(query)):
            f = tf.get(term, 0)
            if f == 0:
                continue
            norm = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            total += self.idf[term] * f * (self.k1 + 1) / norm
        return total

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        """Top-k chunks by score; ties broken by chunk order. Zero-score chunks are excluded."""
        scored = [(self.chunks[i], self.score(query, i)) for i in range(len(self.chunks))]
        scored = [(c, s) for c, s in scored if s > 0]
        scored.sort(key=lambda cs: -cs[1])  # stable sort keeps chunk order for ties
        return scored[:k]

"""Specification tests for Lab 2.2."""

import math

import pytest
from conftest import DATA_DIR

from ctx import retrieval, strategies
from ctx.retrieval import BM25, Chunk

DOC = """# Webhook Delivery

Signatures use HMAC-SHA256.

Failed deliveries are retried 8 times.
"""


def test_tokenize():
    assert retrieval.tokenize("The X-Relay-Signature header, in 2026!") == ["x", "relay", "signature", "header", "2026"]


def test_chunk_document_with_and_without_titles():
    plain = retrieval.chunk_document("webhooks.md", DOC, with_title=False)
    assert [c.chunk_id for c in plain] == ["webhooks.md#1", "webhooks.md#2"]
    assert plain[1].text == "Failed deliveries are retried 8 times."
    titled = retrieval.chunk_document("webhooks.md", DOC)
    assert titled[1].text == "Title: Webhook Delivery\nFailed deliveries are retried 8 times."
    assert all(c.doc == "webhooks.md" for c in titled)


def test_expand_query_appends_unique_synonyms_in_order():
    syn = {"check": ["verify", "signature"], "came": ["signature"]}
    assert retrieval.expand_query("How do I check where it came from?", syn) == \
        "How do I check where it came from? verify signature"
    assert retrieval.expand_query("nothing to expand", syn) == "nothing to expand"


@pytest.fixture
def tiny_index():
    chunks = [Chunk("a#1", "a", "cats purr"), Chunk("b#1", "b", "dogs bark loudly"), Chunk("c#1", "c", "cats and dogs")]
    return BM25(chunks)


def test_bm25_score_matches_formula(tiny_index):
    # N=3, avgdl=(2+3+2)/3. Query "purr" occurs only in chunk 0 (dl=2), df=1.
    idf = math.log(1 + (3 - 1 + 0.5) / (1 + 0.5))
    norm = 1 + 1.5 * (1 - 0.75 + 0.75 * 2 / (7 / 3))
    assert tiny_index.score("purr", 0) == pytest.approx(idf * 1 * 2.5 / norm)
    assert tiny_index.score("purr", 1) == 0.0


def test_bm25_repeated_query_terms_count_once(tiny_index):
    assert tiny_index.score("cats cats cats", 0) == pytest.approx(tiny_index.score("cats", 0))


def test_bm25_search_orders_and_drops_zero_scores(tiny_index):
    hits = tiny_index.search("purr", k=3)
    assert [c.chunk_id for c, _ in hits] == ["a#1"]


def test_answer_in_context_is_case_insensitive_and_needs_the_source():
    ctx = strategies.Context("bm25-k2", (("webhooks.md", "Retried 8 TIMES with backoff"), ("other.md", "15 minutes")))
    assert strategies.answer_in_context("8 times", "webhooks.md", ctx)
    assert not strategies.answer_in_context("9 times", "webhooks.md", ctx)
    # The phrase is present, but in the wrong document: not a hit.
    assert not strategies.answer_in_context("15 minutes", "sso-setup.md", ctx)


def test_reciprocal_rank_requires_the_source_document():
    ranked = [Chunk("a#1", "a", "nothing"), Chunk("x#1", "x", "the answer is 42"),
              Chunk("b#1", "b", "the answer is 42"), Chunk("c#1", "c", "42 again")]
    assert strategies.reciprocal_rank("42", "b", ranked) == pytest.approx(1 / 3)
    assert strategies.reciprocal_rank("43", "b", ranked) == 0.0


# ----------------------------------------------------------- full corpus

@pytest.fixture(scope="module")
def corpus():
    docs = retrieval.load_docs(DATA_DIR / "docs")
    questions = retrieval.load_questions(DATA_DIR / "questions.jsonl")
    titled = BM25([c for n, t in docs.items() for c in retrieval.chunk_document(n, t)])
    plain = BM25([c for n, t in docs.items() for c in retrieval.chunk_document(n, t, with_title=False)])
    synonyms = retrieval.load_synonyms(DATA_DIR / "synonyms.json")
    by_kind = {k: [q for q in questions if q["type"] == k] for k in ("keyword", "paraphrase", "heldout")}
    return docs, by_kind, titled, plain, synonyms


def test_corpus_shape(corpus):
    docs, by_kind, *_ = corpus
    assert len(docs) == 12
    assert {k: len(v) for k, v in by_kind.items()} == {"keyword": 24, "paraphrase": 12, "heldout": 10}


def test_keyword_questions_are_easy_for_bm25(corpus):
    docs, by_kind, titled, _, _ = corpus
    assert strategies.evaluate("bm25", by_kind["keyword"], docs, titled, k=1).answer_in_context == 1.0


def test_paraphrases_expose_the_vocabulary_gap(corpus):
    docs, by_kind, titled, plain, _ = corpus
    assert strategies.evaluate("bm25", by_kind["paraphrase"], docs, plain, k=1).answer_in_context == pytest.approx(5 / 12)
    assert strategies.evaluate("bm25", by_kind["paraphrase"], docs, titled, k=1).answer_in_context == pytest.approx(6 / 12)


def test_tuned_expansion_looks_great_but_does_not_generalize(corpus):
    docs, by_kind, titled, _, syn = corpus
    tuned = strategies.evaluate("bm25", by_kind["paraphrase"], docs, titled, k=3, synonyms=syn)
    heldout_plain = strategies.evaluate("bm25", by_kind["heldout"], docs, titled, k=3)
    heldout_expanded = strategies.evaluate("bm25", by_kind["heldout"], docs, titled, k=3, synonyms=syn)
    assert tuned.answer_in_context == 1.0
    assert heldout_expanded.answer_in_context == heldout_plain.answer_in_context == pytest.approx(0.9)


def test_full_context_always_contains_the_answer_at_fourteen_times_the_tokens(corpus):
    docs, by_kind, titled, plain, _ = corpus
    full = strategies.evaluate("full", by_kind["paraphrase"], docs, None)
    top3 = strategies.evaluate("bm25", by_kind["paraphrase"], docs, plain, k=3)
    assert full.answer_in_context == 1.0
    assert round(full.mean_tokens / top3.mean_tokens) == 14  # 1,531 vs 109 tokens



def test_anatomy_of_a_miss_matches_chapter_2():
    from ctx import explain
    text = explain.explain(DATA_DIR, "P05")
    assert "Query tokens (10)" in text and "Chunks indexed: 36" in text
    assert "sso-setup.md#3: shares 1 token(s) ['out']; rank 3" in text
    assert "1. oncall-escalation.md#2" in text


def test_heldout_titles_do_not_beat_plain_chunks(corpus):
    docs, by_kind, titled, plain, _ = corpus
    p = strategies.evaluate("bm25", by_kind["heldout"], docs, plain, k=3)
    t = strategies.evaluate("bm25", by_kind["heldout"], docs, titled, k=3)
    assert p.answer_in_context == t.answer_in_context == pytest.approx(0.9)
    assert p.mrr_at_k > t.mrr_at_k and p.mean_tokens < t.mean_tokens

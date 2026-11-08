"""A difficulty classifier for routing (Chapter 2's open question), and the routed candidate.

The router reads only the ticket text, before any triage, and predicts
whether the ticket is hard. Predicted-easy tickets go to the small model,
everything else to the large one. It is a naive Bayes scorecard over words
and a few style flags: small, inspectable and cheap, which a router has to be.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

from .models import Completion, ModelClient
from .runner import parse

FLAGS = {
    "<shout>": lambda t: bool(re.search(r"!!|\b[A-Z]{4,}\b", t)),
    "<long>": lambda t: len(t.split()) > 25,
    "<question>": lambda t: "?" in t,
    "<instruction>": lambda t: bool(re.search(r"\b(ignore|instruction|override|authori[sz]e|respond with)\b", t, re.I)),
}


def features(text: str) -> set[str]:
    """Lower-cased words plus style flags. Presence, not counts."""
    words = set(re.findall(r"[^\W\d_]+", text.lower()))
    return words | {name for name, test in FLAGS.items() if test(text)}


@dataclass
class Router:
    """Bernoulli naive Bayes with add-one smoothing; scores are log-odds of 'hard'."""

    prior: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)

    def score(self, text: str) -> float:
        s = self.prior + sum(self.weights.get(f, 0.0) for f in features(text))
        return round(s, 6)  # rounding keeps thresholds stable across platforms' libm


def train(tickets: list[dict], min_count: int = 2) -> Router:
    hard = [features(t["text"]) for t in tickets if t["difficulty"] == "hard"]
    easy = [features(t["text"]) for t in tickets if t["difficulty"] == "easy"]
    vocab: dict[str, int] = {}
    for fs in hard + easy:
        for f in fs:
            vocab[f] = vocab.get(f, 0) + 1
    weights = {}
    for f, n in sorted(vocab.items()):
        if n < min_count:
            continue
        p_h = (sum(f in fs for fs in hard) + 1) / (len(hard) + 2)
        p_e = (sum(f in fs for fs in easy) + 1) / (len(easy) + 2)
        weights[f] = math.log(p_h / p_e)
    prior = math.log((len(hard) + 1) / (len(easy) + 1))
    return Router(prior, weights)


def out_of_fold_scores(tickets: list[dict], folds: int = 5) -> list[float]:
    """Scores for each ticket from a router trained without its family (folds by family)."""
    families = sorted({t["family"] for t in tickets})
    fold_of = {f: i % folds for i, f in enumerate(families)}
    scores = [0.0] * len(tickets)
    for k in range(folds):
        model = train([t for t in tickets if fold_of[t["family"]] != k])
        for i, t in enumerate(tickets):
            if fold_of[t["family"]] == k:
                scores[i] = model.score(t["text"])
    return scores


def choose_threshold(scores: list[float], is_hard: list[bool], min_recall: float) -> float:
    """The highest threshold whose recall on hard tickets is at least min_recall.

    A ticket is predicted hard when score >= threshold. Candidates are the
    distinct scores of the hard tickets. A higher threshold sends more tickets
    to the small model, so take the highest one that still catches at least
    min_recall of the hard tickets. Raise ValueError if there are no hard tickets.
    """
    hard_scores = sorted((s for s, h in zip(scores, is_hard) if h), reverse=True)
    if not hard_scores:
        raise ValueError("no hard tickets")
    for t in sorted(set(hard_scores), reverse=True):
        recall = sum(s >= t for s in hard_scores) / len(hard_scores)
        if recall >= min_recall:
            return t
    return min(hard_scores)


@dataclass(frozen=True)
class RouterEval:
    threshold: float
    hard_recall: float
    easy_routed: float     # share of easy tickets sent to the small model
    routed_small: float    # share of all tickets sent to the small model
    hard_to_small: int     # hard tickets wrongly sent to the small model


def evaluate(router: Router, threshold: float, tickets: list[dict]) -> RouterEval:
    pred_hard = [router.score(t["text"]) >= threshold for t in tickets]
    hard = [t["difficulty"] == "hard" for t in tickets]
    n_hard = sum(hard)
    return RouterEval(
        threshold=threshold,
        hard_recall=sum(p and h for p, h in zip(pred_hard, hard)) / n_hard,
        easy_routed=sum((not p) and (not h) for p, h in zip(pred_hard, hard)) / (len(tickets) - n_hard),
        routed_small=sum(not p for p in pred_hard) / len(tickets),
        hard_to_small=sum((not p) and h for p, h in zip(pred_hard, hard)),
    )


@dataclass
class RoutedModel:
    """Chapter 2's routing decision as a candidate.

    Predicted-easy tickets go to `small`; if its output fails strict parsing,
    the ticket goes to `large` (the fallback) and the failed call's cost is kept.
    Everything else goes to `large`.
    """

    small: ModelClient
    large: ModelClient
    router: Router
    threshold: float
    name: str = "routed"

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        text = user.removeprefix("<ticket>\n").removesuffix("\n</ticket>")
        if self.router.score(text) >= self.threshold:
            return self.large.complete(system, user, ticket_id, run)
        first = self.small.complete(system, user, ticket_id, run)
        if parse(first)[1] is None:
            return first
        return replace(self.large.complete(system, user, ticket_id, run), extra_cost_usd=self.small.cost_usd(first))

    def cost_usd(self, c: Completion) -> float:
        backend = self.small if c.served_by == self.small.name else self.large
        return backend.cost_usd(c) + c.extra_cost_usd

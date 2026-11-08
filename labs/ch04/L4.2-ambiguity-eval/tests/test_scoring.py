"""Specification tests for Lab 4.2: scoring, the missing-actor rule and live-mode outcomes."""

import json

import pytest
from conftest import DATA_DIR

from ambeval import detector, live, scoring
from ambeval.data import Statement, load_lexicon
from ambeval.models import Completion

LEX = load_lexicon(DATA_DIR / "lexicon-v1.json")


def st(sid, defects=(), text="x", set_id="T1", split="dev"):
    return Statement(sid, set_id, split, "t", text, frozenset(defects), None)


# ------------------------------------------------------------ TODO 1: confusion

def test_confusion_counts_by_hand():
    ss = [st("A", ["ambiguity"]), st("B", ["ambiguity", "untestable"]), st("C"), st("D", ["untestable"]), st("E")]
    pred = {"A": frozenset({"ambiguity"}), "C": frozenset({"ambiguity"}), "D": frozenset({"ambiguity", "untestable"})}
    assert scoring.confusion(ss, pred, "ambiguity") == scoring.Counts(tp=1, fp=2, fn=1, tn=1)
    assert scoring.confusion(ss, pred, "untestable") == scoring.Counts(tp=1, fp=0, fn=1, tn=3)


def test_missing_prediction_counts_as_nothing_flagged():
    assert scoring.confusion([st("A", ["contradiction"])], {}, "contradiction") == scoring.Counts(0, 0, 1, 0)


# ------------------------------------------------------------ TODO 2: rates

def test_rates_with_wilson_intervals():
    r = scoring.rates(scoring.Counts(tp=8, fp=2, fn=0, tn=5))
    assert r.precision == pytest.approx(0.8) and r.recall == 1.0
    assert r.precision_ci == pytest.approx((0.4902, 0.9433), abs=1e-3)   # Wilson 8 of 10, as in Lab 2.1
    assert r.recall_ci[1] == pytest.approx(1.0) and r.recall_ci[0] > 0.6


def test_undefined_rates_are_none_not_zero():
    nothing_flagged = scoring.rates(scoring.Counts(tp=0, fp=0, fn=3, tn=4))
    assert nothing_flagged.precision is None and nothing_flagged.precision_ci is None
    assert nothing_flagged.recall == 0.0
    no_positives = scoring.rates(scoring.Counts(tp=0, fp=1, fn=0, tn=4))
    assert no_positives.recall is None and no_positives.recall_ci is None and no_positives.precision == 0.0


def test_wilson_is_chapter_2s():
    lo, hi = scoring.wilson_interval(8, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.4902, 0.9433)
    with pytest.raises(ValueError):
        scoring.wilson_interval(0, 0)


# ------------------------------------------------------------ TODO 3: missing actor

@pytest.mark.parametrize("text", [
    "A summary email is sent at the end of each hour.",
    "Overrides are logged as appropriate.",
    "Exports started during a deploy must be retried automatically.",
])
def test_passive_with_no_actor_is_flagged(text):
    assert detector.detect_missing_actor(text, LEX) is True


@pytest.mark.parametrize("text", [
    "Relay must email each target within 60 seconds.",                     # active voice
    "Repeated violations trigger an alert.",                               # names nobody, but not passive: a known miss
    "A warning is shown to every Admin.",                                  # passive, actor named
    "The rule is approved by the product owner.",                          # passive with "by"
    "A Guest can see only the projects they are invited to.",              # actor term present
])
def test_not_flagged(text):
    assert detector.detect_missing_actor(text, LEX) is False


def test_actor_terms_are_case_sensitive():
    assert detector.detect_missing_actor("The relay race is sent to the owner.", LEX) is True


# ------------------------------------------------------------ provided detector rules

def test_ambiguity_and_untestable_rules():
    assert detector.detect_ambiguity("Notify the relevant people within 10 minutes.", LEX)
    assert not detector.detect_untestable("Notify the relevant people within 10 minutes.", LEX)
    assert detector.detect_untestable("Delivery must be highly available.", LEX)
    assert detector.detect_untestable("The editor should show a preview.", LEX)
    assert not detector.detect_untestable("An Admin can delete a rule.", LEX)


def test_contradiction_rule_needs_overlap_and_a_difference():
    a = st("A", text="SSO sessions must last 12 hours by default.")
    b = st("B", text="SSO sessions must last 8 hours by default.")
    c = st("C", text="Admins can set default notification preferences.")
    assert detector.detect_contradictions([a, b, c], LEX) == {"A", "B"}
    other_set = st("D", text="SSO sessions must last 4 hours by default.", set_id="T2")
    assert detector.detect_contradictions([a, other_set], LEX) == set()


# ------------------------------------------------------------ live mode, without a network

GOOD = json.dumps({"ambiguity": True, "untestable": False, "contradiction": False, "missing_actor": True})


class FakeModel:
    name, price_in_per_mtok, price_out_per_mtok = "fake", 4.0, 20.0

    def __init__(self, completions):
        self.completions, self.calls = list(completions), 0

    def complete(self, system, user):
        self.calls += 1
        return self.completions.pop(0)


def test_every_failure_is_an_outcome_not_a_crash():
    ss = [st(f"S{i}") for i in range(6)]
    model = FakeModel([
        Completion(GOOD, 100, 10, 0.1),
        Completion("", 0, 0, 0.1, "refusal"),
        Completion('{"ambiguity": tr', 100, 1024, 0.1, "max_tokens"),
        Completion("", 0, 0, 0.1, "api_error:RateLimitError"),
        Completion("Sure! " + GOOD, 100, 10, 0.1),
        Completion(json.dumps({"ambiguity": True}), 100, 10, 0.1),
    ])
    records = live.run_live(model, ss, ss, max_usd=1.0)
    assert [r.outcome for r in records] == ["ok", "refusal", "truncated", "api_error", "invalid_json", "schema"]
    assert records[0].flagged == {"ambiguity", "missing_actor"}
    assert all(r.flagged == frozenset() for r in records[1:])


def test_cost_ceiling_stops_calls():
    ss = [st(f"S{i}") for i in range(5)]
    # each call: 1,000,000 input tokens at $4/M = $4.00, so the ceiling of $5 allows two calls
    model = FakeModel([Completion(GOOD, 1_000_000, 0, 0.1)] * 5)
    records = live.run_live(model, ss, ss, max_usd=5.0)
    assert model.calls == 2
    assert [r.outcome for r in records] == ["ok", "ok", "budget_exhausted", "budget_exhausted", "budget_exhausted"]
    assert sum(r.cost_usd for r in records) == pytest.approx(8.0)

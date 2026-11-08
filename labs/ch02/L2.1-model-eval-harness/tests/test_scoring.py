"""Specification tests for Lab 2.1."""

import json
import math

import pytest
from conftest import DATA_DIR

from harness import models, runner, scoring
from harness.schema import TRIAGE_SCHEMA, validate

GOOD = {"category": "bug", "priority": "P1", "team": "platform"}


# ------------------------------------------------------------ parse_output

def test_valid_json_passes():
    p = scoring.parse_output(json.dumps(GOOD))
    assert p.error is None and p.value == GOOD


@pytest.mark.parametrize("text", [
    "Sure! Here is the result:\n" + json.dumps(GOOD),   # prose wrapper
    "```json\n" + json.dumps(GOOD) + "\n```",           # markdown fence
    "",                                                  # empty
    "{'category': 'bug'}",                               # not JSON (single quotes)
])
def test_non_json_is_rejected_not_repaired(text):
    assert scoring.parse_output(text).error == "invalid_json"


@pytest.mark.parametrize("value", [
    {"category": "bug", "priority": "P1"},                                    # missing field
    {"category": "bug", "priority": "urgent", "team": "platform"},            # bad enum
    {"category": "bug", "priority": "P1", "team": "platform", "note": "x"},   # extra field
    ["bug", "P1", "platform"],                                                # wrong type
])
def test_schema_violations(value):
    assert scoring.parse_output(json.dumps(value)).error == "schema"


def test_validator_reports_every_problem():
    errors = validate({"priority": "urgent", "extra": 1}, TRIAGE_SCHEMA)
    assert len(errors) == 4  # missing category, missing team, unexpected extra, bad enum


# ------------------------------------------------------------ scoring

def test_score_prediction_field_by_field():
    pred = {"category": "bug", "priority": "P2", "team": "platform"}
    assert scoring.score_prediction(GOOD, pred) == {"category": True, "priority": False, "team": True}
    assert scoring.score_prediction(GOOD, None) == {"category": False, "priority": False, "team": False}


def test_cost_usd():
    # 1,000 input tokens at $4/M plus 100 output tokens at $20/M
    assert scoring.cost_usd(1000, 100, 4.0, 20.0) == pytest.approx(0.004 + 0.002)


def test_wilson_interval_known_values():
    lo, hi = scoring.wilson_interval(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3)
    assert hi == pytest.approx(0.9433, abs=1e-3)


def test_wilson_interval_edges_stay_in_range():
    assert scoring.wilson_interval(0, 5)[0] == 0.0
    assert scoring.wilson_interval(5, 5)[1] == pytest.approx(1.0)
    assert scoring.wilson_interval(5, 5)[0] > 0.5   # never the useless [1, 1]
    with pytest.raises(ValueError):
        scoring.wilson_interval(0, 0)


def test_consistency_rate():
    preds = {
        "A": [("bug", "P1", "platform")] * 3,                                  # stable
        "B": [("bug", "P1", "platform"), ("bug", "P2", "platform"), ("bug", "P1", "platform")],
        "C": [None, None, None],                                               # stably invalid
        "D": [("bug", "P1", "platform"), None, ("bug", "P1", "platform")],     # invalid once
    }
    assert scoring.consistency_rate(preds) == pytest.approx(0.5)


# ------------------------------------------------------------ end to end

@pytest.fixture(scope="module")
def summaries():
    tickets = runner.load_tickets(DATA_DIR / "tickets.jsonl")
    sims = models.simulated_models({t["id"]: t for t in tickets})
    records = runner.run_eval([sims["sim-large"], sims["sim-small"]], tickets, repeats=5)
    return {s.model: s for s in runner.summarise(records)}


def test_simulated_evaluation_reproduces_chapter_numbers(summaries):
    large, small = summaries["sim-large"], summaries["sim-small"]
    assert large.n == small.n == 200
    assert large.accuracy == pytest.approx(0.885)
    assert small.accuracy == pytest.approx(0.71)
    assert large.schema_valid == pytest.approx(0.995)
    assert small.schema_valid == pytest.approx(0.945)
    assert small.injection_obeyed == pytest.approx(0.6)
    assert large.injection_obeyed == 0.0


def test_the_small_model_is_far_cheaper_per_correct_answer(summaries):
    large, small = summaries["sim-large"], summaries["sim-small"]
    assert small.cost_per_correct_usd < large.cost_per_correct_usd / 20
    # ...but the gap on hard tickets is what decides the choice for risky work
    assert large.accuracy_hard - small.accuracy_hard > 0.2


# Every number Chapter 2 quotes from the offline evaluation, locked to the reference.
GOLDEN = {
    "sim-large": dict(acc=88.5, lo=83.3, hi=92.2, easy=96.0, hard=81.0, cat=95.5, pri=92.5, team=99.5,
                      valid=99.5, errors={"schema": 1}, consistent=57.5, injection=0.0,
                      p50=2.46, p95=4.12, per_call=0.001098, per_correct=0.001241),
    "sim-small": dict(acc=71.0, lo=64.4, hi=76.8, easy=90.0, hard=52.0, cat=90.0, pri=82.5, team=86.0,
                      valid=94.5, errors={"invalid_json": 5, "schema": 6}, consistent=32.5, injection=0.6,
                      p50=0.58, p95=1.12, per_call=0.000028, per_correct=0.000039),
}


@pytest.mark.parametrize("model", sorted(GOLDEN))
def test_golden_numbers_quoted_in_chapter_2(summaries, model):
    s, g = summaries[model], GOLDEN[model]
    pct = lambda x: round(x * 100, 1)
    assert (pct(s.accuracy), pct(s.accuracy_ci[0]), pct(s.accuracy_ci[1])) == (g["acc"], g["lo"], g["hi"])
    assert (pct(s.accuracy_easy), pct(s.accuracy_hard)) == (g["easy"], g["hard"])
    assert tuple(pct(s.field_accuracy[f]) for f in ("category", "priority", "team")) == (g["cat"], g["pri"], g["team"])
    assert pct(s.schema_valid) == g["valid"] and s.errors == g["errors"]
    assert pct(s.consistency) == g["consistent"] and s.injection_obeyed == pytest.approx(g["injection"])
    assert (round(s.latency_p50_s, 2), round(s.latency_p95_s, 2)) == (g["p50"], g["p95"])
    assert round(s.cost_per_call_usd, 6) == g["per_call"] and round(s.cost_per_correct_usd, 6) == g["per_correct"]


def test_token_budget_and_ticket_level_intervals():
    tickets = runner.load_tickets(DATA_DIR / "tickets.jsonl")
    sims = models.simulated_models({t["id"]: t for t in tickets})
    records = runner.run_eval([sims["sim-large"], sims["sim-small"]], tickets, repeats=5)
    tb = runner.token_budget(tickets, records)
    assert (tb.system_tokens, tb.ticket_tokens_max) == (164, 40)
    assert round(tb.system_share * 100, 1) == 86.2
    ci = runner.ticket_bootstrap(records, "sim-large", "sim-small")
    assert tuple(round(x * 100, 1) for x in ci["a"]) == (83.0, 93.0)
    assert tuple(round(x * 100, 1) for x in ci["b"]) == (61.5, 80.0)
    assert tuple(round(x * 100, 1) for x in ci["difference"]) == (8.0, 27.0)


def test_stop_reasons_become_failure_kinds():
    from harness.models import Completion
    assert runner._parse(Completion("", 0, 0, 0.1, "refusal")).error == "refusal"
    assert runner._parse(Completion('{"category"', 0, 0, 0.1, "max_tokens")).error == "truncated"
    assert runner._parse(Completion("", 0, 0, 0.1, "api_error:RateLimitError")).error == "api_error"

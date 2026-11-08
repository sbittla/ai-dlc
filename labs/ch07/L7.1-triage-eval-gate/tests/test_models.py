"""Provided code: the simulator's honesty rules, strict parsing and the live-mode budget guard."""

import pytest
from conftest import DATA_DIR

from evalsuite import models, prompts, runner
from evalsuite.dataset import load_tickets

TICKETS = load_tickets(DATA_DIR / "tickets.jsonl")
GOLD = {t["id"]: t for t in TICKETS}


def test_only_configured_pairs_exist():
    with pytest.raises(ValueError):
        models.SimulatedTriageModel("sim-small", "triage-v2", GOLD)


def test_simulator_is_deterministic():
    a = models.SimulatedTriageModel("sim-large", "triage-v1", GOLD)
    b = models.SimulatedTriageModel("sim-large", "triage-v1", GOLD)
    sys_ = prompts.PROMPTS["triage-v1"].full_system()
    for t in TICKETS[:20]:
        assert a.complete(sys_, t["text"], t["id"], 2) == b.complete(sys_, t["text"], t["id"], 2)


def test_a_ticket_pasted_into_the_prompt_is_copied_not_classified():
    leaked = next(t for t in TICKETS if t["id"] == "T111")
    m = models.SimulatedTriageModel("sim-large", "triage-v3", GOLD)
    recs = runner.run_candidate("x", m, prompts.PROMPTS["triage-v3"], [leaked], 3)
    assert all(r.correct for r in recs)


@pytest.mark.parametrize("stop, kind", [("refusal", "refusal"), ("max_tokens", "truncated"),
                                        ("api_error:RateLimitError", "api_error"), ("budget_exceeded", "budget")])
def test_stop_reasons_become_failure_kinds(stop, kind):
    assert runner.parse(models.Completion('{"category": "bug"}', 0, 0, 0.0, stop)) == (None, kind)


def test_parse_never_repairs():
    assert runner.parse(models.Completion('Sure! {"category": "bug"}', 0, 0, 0.0)) == (None, "invalid_json")


class Fixed:
    name = "fixed"

    def complete(self, system, user, ticket_id, run):
        return models.Completion("{}", 1_000_000, 0, 0.0, served_by="fixed")

    def cost_usd(self, c):
        return 1.0


def test_budget_guard_records_refusals_instead_of_spending():
    g = models.BudgetGuard(Fixed(), max_usd=2.5, est_call_usd=1.0)
    stops = [g.complete("s", "u", "T", i).stop_reason for i in range(4)]
    assert stops == ["end_turn", "end_turn", "budget_exceeded", "budget_exceeded"]
    assert g.spent_usd == 2.0


def test_live_prices_cover_the_models_the_chapter_names():
    assert {"claude-opus-5-5", "claude-haiku-5-5"} <= set(models.LIVE_PRICES)
    with pytest.raises(ValueError):
        models.live_model("claude-unknown")

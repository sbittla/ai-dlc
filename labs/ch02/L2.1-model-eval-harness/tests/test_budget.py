"""Tests for the live-mode spend guard (provided infrastructure). A fake client stands in for the
Anthropic SDK, so these tests make no network calls and need no credentials or `anthropic` package."""

import math
import sys
import types
from types import SimpleNamespace

import pytest

from harness import models, prompt, runner


class FakeMessages:
    """Bills every call at max_tokens, with input at 2.7 characters per token (pessimistic)."""

    def __init__(self, output_tokens=None):
        self.calls = 0
        self.output_tokens = output_tokens

    def create(self, *, model, max_tokens, system, messages, output_config):
        self.calls += 1
        chars = len(system) + sum(len(m["content"]) for m in messages)
        out = max_tokens if self.output_tokens is None else self.output_tokens
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"category": "bug", "priority": "P1", "team": "platform"}')],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=math.ceil(chars / 2.7), output_tokens=out),
        )


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Install a stand-in `anthropic` module, so the live adapter never imports the real SDK."""
    module = types.ModuleType("anthropic")
    module.APIError = type("APIError", (Exception,), {})
    module.Anthropic = lambda: pytest.fail("the test must inject a fake client")
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return module


def guarded(model_id, max_usd, messages):
    g = models.BudgetGuard(models.live_model(model_id), max_usd)
    g.inner._client = SimpleNamespace(messages=messages)
    return g


def ask(g, n):
    user = prompt.user_message("The export button does nothing when I click it.")
    return [g.complete(prompt.SYSTEM, user, f"TK{i:02d}", 1) for i in range(n)]


def test_worst_case_estimate_covers_a_max_tokens_reply():
    user = prompt.user_message("x" * 500)
    worst = models.worst_case_call_usd(prompt.SYSTEM, user, 4.00, 20.00, 1024)
    assert worst >= 1024 * 20.00 / 1_000_000 + len(prompt.SYSTEM + user) / 2.7 * 4.00 / 1_000_000


def test_guard_refuses_before_calling_when_worst_case_does_not_fit(fake_anthropic):
    messages = FakeMessages()
    g = guarded("claude-opus-5-5", 0.01, messages)  # less than one worst-case Opus call (> $0.02)
    (c,) = ask(g, 1)
    assert c.stop_reason == "budget_exceeded"
    assert messages.calls == 0 and g.spent_usd == 0 and g.refused == 1


def test_spend_never_passes_the_ceiling_at_worst_case(fake_anthropic):
    messages = FakeMessages()
    g = guarded("claude-opus-5-5", 0.10, messages)
    results = ask(g, 20)
    assert 0 < messages.calls < 20
    assert g.refused == 20 - messages.calls
    assert g.spent_usd <= 0.10
    # stops only when the next call might not fit
    worst = models.worst_case_call_usd(prompt.SYSTEM, prompt.user_message("The export button does nothing when I click it."),
                                       4.00, 20.00, 1024)
    assert g.spent_usd + worst > 0.10
    assert [c.stop_reason for c in results[messages.calls:]] == ["budget_exceeded"] * g.refused


def test_typical_calls_all_run_and_spend_is_counted(fake_anthropic):
    messages = FakeMessages(output_tokens=60)
    g = guarded("claude-haiku-5-5", 0.10, messages)
    results = ask(g, 10)
    assert messages.calls == 10 and g.refused == 0
    expected = sum(c.input_tokens * 0.10 + c.output_tokens * 0.50 for c in results) / 1_000_000
    assert g.spent_usd == pytest.approx(expected)


def test_budget_is_split_equally_between_models():
    gs = models.guarded_live_models(["claude-opus-5-5", "claude-haiku-5-5"], 2.00)
    assert [g.name for g in gs] == ["claude-opus-5-5", "claude-haiku-5-5"]
    assert [g.max_usd for g in gs] == [1.00, 1.00]
    assert gs[0].price_out_per_mtok == 20.00


def test_a_refused_call_is_recorded_as_a_budget_failure():
    c = models.Completion("", 0, 0, 0.0, stop_reason="budget_exceeded")
    assert runner._parse(c).error == "budget"

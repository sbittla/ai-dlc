"""Tests for live-mode pricing and the spend ceiling (provided infrastructure). A fake client stands in
for the Anthropic SDK: no network, no credentials, no `anthropic` package needed."""

import math
import sys
import types
from types import SimpleNamespace

import pytest
from conftest import DATA_DIR

from ctx import report


class FakeMessages:
    """Bills every call at max_tokens, with input at 2.7 characters per token (pessimistic)."""

    def __init__(self):
        self.calls = 0

    def create(self, *, model, max_tokens, output_config, messages):
        self.calls += 1
        chars = sum(len(m["content"]) for m in messages)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="placeholder")], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=math.ceil(chars / 2.7), output_tokens=max_tokens))


@pytest.fixture
def fake_anthropic(monkeypatch):
    module = types.ModuleType("anthropic")
    module.APIError = type("APIError", (Exception,), {})
    module.Anthropic = lambda: pytest.fail("the test must inject a fake client")
    monkeypatch.setitem(sys.modules, "anthropic", module)


def test_each_model_has_its_own_input_and_output_price():
    assert report.LIVE_PRICES["claude-haiku-5-5"] == (0.10, 0.50)
    assert report.LIVE_PRICES["claude-opus-5-5"] == (4.00, 20.00)
    assert report.call_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)


def test_offline_context_cost_still_uses_the_large_model_input_price():
    assert report.LIVE_PRICES[report.CONTEXT_COST_MODEL][0] == 4.00


def test_worst_case_bills_every_output_token():
    assert report.worst_case_call_usd("claude-opus-5-5", "x" * 2000) == pytest.approx(
        (1000 * 4.00 + report.LIVE_MAX_TOKENS * 20.00) / 1_000_000)


def test_unknown_model_is_refused_before_any_call():
    with pytest.raises(ValueError):
        report.live(DATA_DIR, "claude-unknown", client=object())


def test_live_spend_never_passes_the_ceiling(fake_anthropic):
    messages = FakeMessages()
    try:
        out = report.live(DATA_DIR, "claude-opus-5-5", max_usd=0.20, client=SimpleNamespace(messages=messages))
    except NotImplementedError:
        pytest.skip("needs your retrieval implementation")
    spent = float(out.rsplit("Live spend $", 1)[1].split()[0])
    assert 0 < messages.calls < 3 * 46
    assert spent <= 0.20

"""The optional live mode refuses to touch a real account unless every gate is explicit. Nothing here runs tofu."""

import importlib.util

import pytest
from conftest import LAB_ROOT

spec = importlib.util.spec_from_file_location("live11", LAB_ROOT / "scripts" / "live_mode.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
OK = ["--account-id", "123456789012", "--email", "me@example.com"]


def test_dry_run_only_prints(capsys, monkeypatch):
    monkeypatch.setattr(live, "run", lambda args: pytest.fail("must not execute"))
    assert live.main(["apply", *OK], env={}) == 0
    out = capsys.readouterr().out
    assert "would run: tofu apply -input=false live.tfplan" in out
    assert "-var=service_desired_count=0" in out and "-exclude=aws_lb_listener.https" in out


@pytest.mark.parametrize("argv, env, reason", [
    (["plan", "--account-id", "111122223333", "--email", "a@b.c"], {}, "the book's example"),
    (["apply", *OK, "--execute"], {}, "LAB11_LIVE=1"),
    (["apply", *OK, "--execute", "--max-usd", "5"], {"LAB11_LIVE": "1"}, "--i-accept-charges"),
    (["apply", *OK, "--execute", "--i-accept-charges", "--max-usd", "50"], {"LAB11_LIVE": "1"}, "--max-usd"),
    (["apply", *OK, "--execute", "--i-accept-charges", "--max-usd", "5", "--hours", "24"], {"LAB11_LIVE": "1"},
     "--hours"),
])
def test_refusals(argv, env, reason, capsys, monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/tofu")
    monkeypatch.setattr(live, "run", lambda args: pytest.fail("must not execute"))
    assert live.main(argv, env=env) == 2
    assert reason in capsys.readouterr().err


def test_refuses_without_opentofu(capsys, monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: None)
    assert live.main(["plan", *OK, "--execute"], env={"LAB11_LIVE": "1"}) == 2
    assert "not on PATH" in capsys.readouterr().err


def test_ceiling_uses_the_lab_estimator():
    import json
    plan = json.loads((LAB_ROOT / "data" / "plans" / "relay-nonprod.plan.json").read_text(encoding="utf-8"))
    ok, cost = live.within_ceiling(plan, 2.0, 5.0)
    assert ok and round(cost, 2) == 0.61

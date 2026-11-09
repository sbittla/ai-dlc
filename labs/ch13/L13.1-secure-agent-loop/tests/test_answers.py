"""The arithmetic behind book/answers/ch13-answers.md, Exercises 5 and 6 (Lab 13.1)."""

import secloop
from secloop import DATA, load_json, loop
from secloop.catch import catch_report

TRUTH = load_json(DATA / "changes" / "truth.json")["changes"]


def run_with(edit, monkeypatch):
    policy = secloop.gate_policy()
    edit(policy)
    monkeypatch.setattr(loop, "gate_policy", lambda: policy)
    return catch_report(loop.run(), TRUTH)


def test_exercise_5_raising_the_blocking_threshold_to_8(monkeypatch):
    rep = run_with(lambda p: p.update(block_at_or_above=8.0), monkeypatch)
    assert (rep.total.caught, rep.total.pre_commit, rep.clean_blocked) == (61, 59, 1)
    caught = {r.name: r.caught for r in rep.rows}
    assert (caught["weak-crypto"], caught["path-traversal"], caught["vulnerable-dependency"],
            caught["iac-misconfiguration"], caught["hardcoded-secret"]) == (0, 0, 0, 2, 10)


def test_exercise_6_dependency_gate_in_ci_only(monkeypatch):
    rep = run_with(lambda p: p["stages"]["pre-commit"].update(scanners=["gitleaks", "semgrep"]), monkeypatch)
    assert (rep.total.caught, rep.total.pre_commit) == (83, 51)

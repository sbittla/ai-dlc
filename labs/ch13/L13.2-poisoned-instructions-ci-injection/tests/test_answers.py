"""The arithmetic behind book/answers/ch13-answers.md, Exercise 7 (Lab 13.2)."""

import copy

from poisonlab import DATA, load_json
from poisonlab.ciagent import config_from_workflow, outcome

CASES = load_json(DATA / "ci-attacks" / "cases.json")["cases"]
V2 = config_from_workflow((DATA / "workflows" / "agent-on-comment.v2.yml").read_text(encoding="utf-8"))


def winners(**changes):
    cfg = copy.deepcopy(V2)
    for k, v in changes.items():
        setattr(cfg, k, v)
    return [c["id"] for c in CASES if outcome(c, cfg)[0]]


def test_exercise_7_two_and_three_controls_removed():
    assert winners(author_gate=None, strip_hidden=False) == ["C10", "C11"]
    assert winners(author_gate=None, strip_hidden=False, link_filter=False) == ["C09", "C10", "C11"]

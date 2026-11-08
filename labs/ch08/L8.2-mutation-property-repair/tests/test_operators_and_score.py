"""Mutation operators and the score, on inputs you can check by hand."""

import pytest

from mutate.operators import mutants
from mutate.runner import Outcome
from mutate.score import Score, gate, score

SOURCE = '''"""A docstring: never mutated."""


def f(x: int = 3) -> bool:
    if not x:
        raise ValueError("no")
    return x + 1 <= 10 and True
'''


def test_every_operator_appears_once_per_site_in_a_stable_order():
    found = [(m.line, m.operator, m.change) for m in mutants(SOURCE, "f.py")]
    assert found == [
        (4, "CRP", "3 -> 2"), (4, "CRP", "3 -> 4"),
        (5, "NEG", "not x -> x"),
        (6, "RSD", "raise -> pass"),
        (7, "AOR", "+ -> -"),        # three nodes start at column 11; ties sort by operator name
        (7, "LCR", "and -> or"),
        (7, "ROR", "<= -> <"),
        (7, "CRP", "1 -> 0"), (7, "CRP", "1 -> 2"),
        (7, "CRP", "10 -> 11"), (7, "CRP", "10 -> 9"),
        (7, "CRP", "True -> False"),
    ]


def test_annotations_docstrings_and_raise_arguments_are_left_alone():
    changes = [m.change for m in mutants(SOURCE, "f.py")]
    assert not any("int" in c or "docstring" in c or "'no'" in c for c in changes)


def test_each_mutant_is_one_change_and_still_parses():
    import ast
    for m in mutants(SOURCE, "f.py"):
        ast.parse(m.source)
        assert m.id.startswith(f"f.py:{m.line}:")
    assert len({m.id for m in mutants(SOURCE, "f.py")}) == len(mutants(SOURCE, "f.py"))


def test_chained_comparisons_mutate_each_operator():
    changes = [m.change for m in mutants("def g(a):\n    return 1 < a == 2\n", "g.py") if m.operator == "ROR"]
    assert changes == ["< -> <=", "== -> !="]


class _M:
    def __init__(self, id_):
        self.id = id_


def outcome(id_, status):
    return Outcome(_M(id_), status)


def test_score_counts_killed_over_mutants_minus_recorded_equivalents():
    outs = [outcome("a", "killed"), outcome("b", "killed"), outcome("c", "survived"), outcome("d", "not_covered"),
            outcome("e", "survived")]
    s = score("m", outs, {"e": {"reason": "r", "reviewed_by": "x"}})
    assert (s.mutants, s.killed, s.survived, s.not_covered, s.equivalent) == (5, 2, 1, 1, 1)
    assert s.score == pytest.approx(2 / 4) and s.raw == pytest.approx(2 / 5)


def test_a_killed_mutant_listed_as_equivalent_counts_as_killed():
    s = score("m", [outcome("a", "killed")], {"a": {"reason": "r", "reviewed_by": "x"}})
    assert (s.killed, s.equivalent, s.score) == (1, 0, 1.0)


def test_the_threshold_is_inclusive():
    assert gate([Score("m", 10, 9, 1, 0, 0)], 0.9) == []
    assert gate([Score("m", 10, 8, 2, 0, 0)], 0.9) == ["m: 80.0% is below 90%"]


def test_an_uncovered_mutant_cannot_be_claimed_as_equivalent():
    s = score("m", [outcome("a", "killed"), outcome("b", "not_covered")], {"b": {"reason": "r", "reviewed_by": "x"}})
    assert (s.not_covered, s.equivalent, s.score) == (1, 0, 0.5)

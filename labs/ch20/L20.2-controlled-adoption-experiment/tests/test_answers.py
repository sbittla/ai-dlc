"""Locks the numbers in book/answers/ch20-answers.md, Exercise 7."""

from experiment.power import simulate_power, variance_components, weeks_for_power
from experiment.report import baseline_rows, team_sizes


def test_exercise_7_a_longer_pilot():
    comps = variance_components(baseline_rows())
    sizes = team_sizes()
    assert simulate_power("D3", comps, sizes, 0.85, weeks=26) == 0.827
    assert simulate_power("D3", comps, sizes, 0.85, weeks=26, assumptions={"contamination_task": 0.4}) == 0.576
    assert weeks_for_power("D3", comps, sizes, 0.85) == 23

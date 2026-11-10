"""The arithmetic behind book/answers/ch18-answers.md, Exercises 4 and 7 (Lab 18.2)."""

import math

from servelab.engine import sweep


def test_exercise_4_batch_of_64_against_one():
    assert round(16.5 / 12.1 - 1, 2) == 0.36  # Table 18.9's rounded step times


def test_exercise_7_tenfold_volume():
    rows = sweep()
    best = {(e, p): max(s.rate for s in rows if s.engine == e and s.precision == p and s.meets_slo)
            for e, p in (("static", "fp16"), ("continuous", "fp16"), ("continuous", "int4"))}
    assert list(best.values()) == [2.0, 16.0, 32.0]  # Table 18.10's highest rates meeting the target
    replicas = [math.ceil(5.3 / r) + 1 for r in best.values()]
    assert replicas == [4, 2, 2]
    cost = [n * 730 * 0.80 for n in replicas]
    assert cost == [2336.0, 1168.0, 1168.0]
    api = round(311_460 * 0.002183, 2)
    assert api == 679.92
    assert [round(c / api, 1) for c in cost] == [3.4, 1.7, 1.7]

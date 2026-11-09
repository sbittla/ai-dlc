"""The arithmetic behind book/answers/ch17-answers.md, Exercises 6 and 7 (Lab 17.2)."""

import statistics


from costlab import production
from costlab.compare import run_config, summarize


def test_exercise_6_cost_per_correct_and_refunded_timeouts():
    c = summarize("routed", run_config("routed"))
    assert round(c.usd_per_call * c.calls_per_run / c.quality, 6) == 0.005018
    outs = run_config("reasoner")
    billed = sum(production.call("sim-reasoner", production.gold()[o.ticket_id], o.run, k, 2048).usd
                 for o in outs for k, lat in enumerate(o.call_latencies, 1) if lat <= 10.0)
    per_correct = billed / sum(o.result == "correct" for o in outs)
    a = summarize("large", run_config("large"))
    assert (round(per_correct, 6), round(per_correct / a.usd_per_correct, 2)) == (0.005397, 2.15)


def test_exercise_7_busy_workers():
    busy = {c: statistics.mean(sum(min(x, 10.0) for x in o.call_latencies) for o in run_config(c))
            for c in ("large", "reasoner")}
    assert (round(busy["large"], 3), round(busy["reasoner"], 3)) == (2.354, 7.028)
    assert (round(31.8 / 60 * busy["large"], 2), round(31.8 / 60 * busy["reasoner"], 2)) == (1.25, 3.73)

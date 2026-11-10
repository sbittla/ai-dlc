"""The arithmetic behind book/answers/ch18-answers.md, Exercises 5 and 6 (Lab 18.1)."""

from opslab import replay


def test_exercise_5_backoff_ceilings_delays_and_the_longest_wait():
    ceilings = [min(600, 15 * 2 ** (n - 1)) for n in range(1, 8)]
    assert ceilings == [15, 30, 60, 120, 240, 480, 600]
    delays = [0.20 * 15, max(0.55 * 30, 30), 0.90 * 60]
    assert [round(d, 1) for d in delays] == [3.0, 30.0, 54.0]
    assert sum(ceilings[:5]) == 465  # six attempts have five waits between them; each wait is below its ceiling


TICKETS = [{"ticket_id": c, "charge_id": c, "amount_usd": a, "eligible": True}
           for c, a in (("A", 60), ("B", 90), ("C", 45), ("D", 120), ("E", 36))]
DELIVERIES = [
    {"charge_id": "A", "cause": "first", "processing_s": 70}, {"charge_id": "B", "cause": "first", "processing_s": 20},
    {"charge_id": "C", "cause": "first", "processing_s": 65}, {"charge_id": "D", "cause": "first", "processing_s": 30},
    {"charge_id": "E", "cause": "first", "processing_s": 30},
    {"charge_id": "B", "cause": "webhook_duplicate", "processing_s": 20},
    {"charge_id": "A", "cause": "visibility_timeout", "processing_s": 61},
    {"charge_id": "C", "cause": "visibility_timeout", "processing_s": 30},
    {"charge_id": "A", "cause": "visibility_timeout", "processing_s": 30},
]


def test_exercise_6_refunds_and_extra_dollars_by_control():
    rows = {layers: replay.with_controls(TICKETS, DELIVERIES, layers)
            for layers in ((), ("dedup",), ("heartbeat",), ("ledger",))}
    assert [(s.refunds, s.extra_usd) for s in rows.values()] == [(9, 255), (8, 165), (6, 90), (5, 0)]

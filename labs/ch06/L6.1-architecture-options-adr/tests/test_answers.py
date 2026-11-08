"""Locks the arithmetic in book/answers/ch06-answers.md (Exercises 5-7)."""

import sys
from dataclasses import replace
from datetime import datetime, timezone

from conftest import DATA_DIR, RELAY

from archscore import structure
from archscore.model import Score, load_catalogue, load_options
from archscore.scoring import weight_to_flip, weighted_score

CAT = load_catalogue(DATA_DIR / "drivers.json")
A, B = load_options([DATA_DIR / "options" / "A-modular-monolith.json", DATA_DIR / "options" / "B-microservices.json"])


def test_exercise_5_availability():
    rows = {n: (round(100 * 0.999 ** n, 2), round(structure.unavailable_minutes(0.999 ** n), 1)) for n in (2, 4, 7)}
    assert rows == {2: (99.8, 86.4), 4: (99.6, 172.5), 7: (99.3, 301.5)}
    need = 0.998001 ** (1 / 7)
    assert (round(100 * need, 4), round(structure.unavailable_minutes(need), 1)) == (99.9714, 12.3)


def test_exercise_6_rescoring():
    scores = dict(B.scores, **{"ESC-N07": Score(2, ""), "ESC-N03": Score(2, "")})
    b2 = replace(B, scores=scores)
    assert (weighted_score(b2, CAT.drivers).total, weighted_score(A, CAT.drivers).total) == (58, 75)
    assert set(weight_to_flip(A, b2, CAT.drivers).values()) == {None}
    heavy = tuple(replace(d, weight=5) if d.id in ("CON-3", "CON-6") else d for d in CAT.drivers)
    assert (weighted_score(A, heavy).total, weighted_score(b2, heavy).total, weighted_score(A, heavy).maximum) == \
        (91, 82, 117)


def test_exercise_7_timeline():
    sys.path.insert(0, str(RELAY / "src"))
    from relay.worker import IdempotencyConflict, TriageQueue
    from relay.worker.runner import Worker
    from relay.worker.triage import TriageOutcome

    t0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    q = TriageQueue(":memory:")
    assert q.enqueue("ws", "ticket-0001", "Locked out", t0)[1] is True
    assert q.enqueue("ws", "ticket-0001", "Locked out", t0 + 5)[1] is False
    try:
        q.enqueue("ws", "ticket-0001", "Locked out again", t0 + 6)
        raise AssertionError("expected a conflict")
    except IdempotencyConflict:
        pass

    class Down:
        model, prompt = "scripted", "p"

        def classify(self, text, attempt):
            return TriageOutcome("", 0.0, "unavailable")

    clock = {"t": t0 + 10}
    w = Worker(q, Down(), clock=lambda: clock["t"])
    seen = []
    while len(seen) < 3:
        outcome = w.run_once()
        if outcome != "idle":
            seen.append((datetime.fromtimestamp(clock["t"], timezone.utc).strftime("%H:%M:%S"), outcome))
        clock["t"] += 1
    assert seen == [("10:00:10", "retry"), ("10:00:20", "retry"), ("10:00:40", "needs_human")]
    assert q.counts()["needs_human"] == 1 and sum(q.counts().values()) == 1

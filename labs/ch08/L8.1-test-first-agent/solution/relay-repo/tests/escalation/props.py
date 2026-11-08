"""A very small property-based testing helper, standard library only (test-strategy.md).

    @for_all(integers(5, 240), sampled_from(ZONES), runs=300)
    def test_something(delay, zone): ...

Each run draws arguments from seeded generators, so a failure reproduces
exactly. On failure the helper shrinks the example, trying simpler values one
argument at a time, and reports the smallest failing case it found.

What a real library such as Hypothesis adds: many more generators, smarter
shrinking of nested data, a database of past failures, health checks for slow
or filtered generators, and stateful testing. This helper exists so that
Relay's suite keeps no third-party dependency (ADR-008, AR5).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta


class Gen:
    def __init__(self, draw, shrink=lambda value: []):
        self.draw, self.shrink = draw, shrink


def integers(lo: int, hi: int) -> Gen:
    def shrink(v):
        return [c for c in dict.fromkeys([lo, (lo + v) // 2, v - 1]) if lo <= c < v]
    return Gen(lambda rng: rng.randint(lo, hi), shrink)


def sampled_from(values) -> Gen:
    values = list(values)
    return Gen(lambda rng: rng.choice(values), lambda v: values[: values.index(v)][:3])


def minutes_between(start: datetime, end: datetime) -> Gen:
    """Whole-minute instants in [start, end)."""
    span = int((end - start).total_seconds() // 60)
    ints = integers(0, span - 1)
    return Gen(lambda rng: start + timedelta(minutes=ints.draw(rng)),
               lambda v: [start + timedelta(minutes=m) for m in ints.shrink(int((v - start).total_seconds() // 60))])


def lists(gen: Gen, min_size: int, max_size: int) -> Gen:
    def draw(rng):
        return [gen.draw(rng) for _ in range(rng.randint(min_size, max_size))]

    def shrink(v):
        return [v[:i] + v[i + 1:] for i in range(len(v))] if len(v) > min_size else []
    return Gen(draw, shrink)


def for_all(*gens: Gen, runs: int = 200, seed: int = 20261130):
    def decorate(test):
        def wrapper():
            rng = random.Random(seed)
            for run in range(runs):
                args = [g.draw(rng) for g in gens]
                if _fails(test, args):
                    raise AssertionError(f"property failed on run {run + 1} of {runs} (seed {seed}); "
                                         f"smallest failing example: {_shrink(test, gens, args)!r}")
        # Copy the name but not the signature: pytest must not treat the test's parameters as fixtures.
        wrapper.__name__, wrapper.__qualname__, wrapper.__doc__ = test.__name__, test.__qualname__, test.__doc__
        wrapper.__module__ = test.__module__
        return wrapper
    return decorate


def _fails(test, args) -> bool:
    try:
        test(*args)
    except AssertionError:
        return True
    return False


def _shrink(test, gens, args, budget: int = 200):
    args = list(args)
    improved = True
    while improved and budget > 0:
        improved = False
        for i, gen in enumerate(gens):
            for candidate in gen.shrink(args[i]):
                budget -= 1
                trial = args[:i] + [candidate] + args[i + 1:]
                if _fails(test, trial):
                    args, improved = trial, True
                    break
    return tuple(args)

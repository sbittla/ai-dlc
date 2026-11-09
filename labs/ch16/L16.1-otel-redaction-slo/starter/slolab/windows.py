"""Sliding-window sums over a per-minute series (TODO 2 is `window_sums`)."""

from __future__ import annotations


def window_sums(values: list[int], minutes: int) -> list[int]:
    """TODO 2. For each minute i, the sum of values[i - minutes + 1 .. i] (fewer at the start of the series).

    Use prefix sums, so the whole list costs one pass whatever the window: prefix[k] is the sum of the first k
    values, and the window ending at i is prefix[i + 1] - prefix[max(0, i + 1 - minutes)].
    """
    raise NotImplementedError("TODO 2: window_sums")

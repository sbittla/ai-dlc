"""Sliding-window sums over a per-minute series (TODO 2 is `window_sums`)."""

from __future__ import annotations


def window_sums(values: list[int], minutes: int) -> list[int]:
    """TODO 2. For each minute i, the sum of values[i - minutes + 1 .. i] (fewer at the start of the series).

    Use prefix sums, so the whole list costs one pass whatever the window: prefix[k] is the sum of the first k
    values, and the window ending at i is prefix[i + 1] - prefix[max(0, i + 1 - minutes)].
    """
    if minutes < 1:
        raise ValueError("a window is at least one minute")
    prefix = [0]
    for v in values:
        prefix.append(prefix[-1] + v)
    return [prefix[i + 1] - prefix[max(0, i + 1 - minutes)] for i in range(len(values))]

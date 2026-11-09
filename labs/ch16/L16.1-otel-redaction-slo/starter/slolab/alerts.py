"""Three ways to alert on the same series, and how to score them (TODO 3 and TODO 4).

- static: page when the bad share over the last `window` minutes is above a fixed ratio (often the SLO's
  budget itself, 0.1% for 99.9%). The usual first attempt.
- single-window burn rate: page while the burn rate over one window is at least a rate.
- multi-window, multi-burn-rate: the Site Reliability Workbook's table; each row needs its long window and its
  short window (one twelfth as long) to burn at least its rate, and a page is open while any page row fires.

An *episode* is a run of consecutive minutes in which an alert fires: (action, start, end), inclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

from .windows import window_sums


@dataclass(frozen=True)
class Row:
    long: int
    short: int
    rate: float
    action: str


WORKBOOK = (Row(60, 5, 14.4, "page"), Row(360, 30, 6.0, "page"), Row(4320, 360, 1.0, "ticket"))


def episodes(firing: list[bool], action: str) -> list[tuple[str, int, int]]:
    """Runs of True as (action, start, end), inclusive (provided)."""
    out, start = [], None
    for i, f in enumerate(firing):
        if f and start is None:
            start = i
        if not f and start is not None:
            out.append((action, start, i - 1))
            start = None
    if start is not None:
        out.append((action, start, len(firing) - 1))
    return out


def static_alerts(bad: list[int], total: list[int], ratio: float, window: int,
                  min_events: int = 0) -> list[tuple[str, int, int]]:
    """Provided: page while bad/total over the last `window` minutes is above `ratio`."""
    b, t = window_sums(bad, window), window_sums(total, window)
    return episodes([tt >= max(1, min_events) and bb / tt > ratio for bb, tt in zip(b, t)], "page")


def burn_alerts(bad: list[int], total: list[int], target: float, rows: tuple[Row, ...],
                min_events: int = 0) -> list[tuple[str, int, int]]:
    """TODO 3. Episodes for a burn-rate policy, page episodes first in time order, then ticket episodes.

    A row fires at minute i when the long window has at least max(1, min_events) events and both windows burn
    at least `rate`: (bad / total) / (1 - target) >= rate in the long window and in the short window. A short
    window with no events burns at 0. For each action, an alert fires at i when any row with that action fires.
    Return the episodes of each action (use `episodes`), all sorted by (start, action).
    """
    raise NotImplementedError("TODO 3: burn_alerts")


@dataclass(frozen=True)
class Score:
    detected: list[str]          # event IDs with at least one episode
    missed: list[str]            # significant events with none
    false_alarms: int            # episodes that match no event
    detect_minutes: dict         # event ID -> minutes from event start to the first matching episode's start
    reset_minutes: dict          # event ID -> minutes from event end to the last matching episode's end
    episodes: int


def score(found: list[tuple[str, int, int]], events: list[dict], action: str = "page",
          grace: int = 60) -> Score:
    """TODO 4. Score the episodes with `action` against labelled events.

    `events` are dicts with `id`, `start`, `end` (minute indexes, inclusive) and `significant` (bool). An
    episode matches an event when it overlaps [start, end + grace]. An episode that matches no event is a false
    alarm. `detected` lists, in event order, every event matched by at least one episode; `missed` lists the
    significant events matched by none. Detection minutes: first matching episode's start minus the event's
    start. Reset minutes: last matching episode's end minus the event's end (negative if it stopped early).
    """
    raise NotImplementedError("TODO 4: score")

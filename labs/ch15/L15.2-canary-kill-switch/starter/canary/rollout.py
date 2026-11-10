"""A progressive rollout, minute by minute (TODO 2 in starter/), and the all-at-once comparison (provided).

`run_canary` walks relay-canary-v1's steps (5%, 25%, 50%, 100%; 15 minutes each, the last 0):

- each minute it draws the minute's traffic at the current share and asks `minute_verdict`, with the canary's
  last five minutes (this one included) as the window;
- "ok" advances the step's clock; when the clock reaches the step's bake minutes, the next step starts next
  minute; reaching the last step (bake 0) promotes the release at that minute;
- "bad:*" adds to a streak; at policy["rollback_sustained_minutes"] in a row the release is rolled back at that
  minute. Any other verdict resets the streak;
- "both:*" holds the step and pages, at most once in PAGE_GROUP_MINUTES (Chapter 16's relay-alert-routing-v1
  groups pages for 60 minutes); "stable:*" and "too-few" hold the step without a page;
- only an "ok" minute advances the step's clock. Every held minute counts towards policy["max_hold_minutes"]
  for the step (a later "ok" minute does not reset the count); at that many, the release is rolled back:
  "rolled back: not judged" when the minute is "too-few", else "rolled back: shared problem did not clear".

Exposure counts what users got from the canary until the decision: its requests, and its bad answers (errors
plus slow answers).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import minute_verdict
from .traffic import Counts, minute_counts

PAGE_GROUP_MINUTES = 60


@dataclass
class Result:
    scenario: str
    decision: str                 # promoted | rolled back | rolled back: not judged | undecided
    minute: int | None            # minute of the decision
    percent: int                  # canary share at the decision
    canary: Counts = field(default_factory=Counts)
    pages: list[int] = field(default_factory=list)
    events: list[tuple[int, str]] = field(default_factory=list)

    @property
    def bad_served(self) -> int:
        return self.canary.errors + self.canary.slow


def run_canary(scn: dict, policy: dict, slos: dict) -> Result:
    raise NotImplementedError("TODO 2: run_canary")


def run_all_at_once(scn: dict, policy: dict, slos: dict) -> Result:
    """The train's shape (provided): the new version takes all traffic at minute 0. The same burn rule detects a
    problem (on the new version's own minutes, three in a row), and a person rolls back, which takes the
    scenario's `manual_rollback_minutes` (an assumption). Exposure runs until the rollback completes."""
    limit, need = policy["rollback_burn_rate"], policy["rollback_sustained_minutes"]
    res = Result(scn["id"], "undecided", None, 100)
    streak, detected = 0, None
    for minute in range(scn["max_minutes"]):
        if detected is not None and minute > detected + scn["manual_rollback_minutes"]:
            res.decision, res.minute = "rolled back", minute
            return res
        _, new = minute_counts(scn, minute, 1.0)
        res.canary = res.canary + new
        bad = any(new.requests and (b := _burn(new, s, slos[s]["target"])) is not None and b >= limit
                  for s in policy["signals"])
        streak = streak + 1 if bad else 0
        if detected is None and streak >= need:
            detected = minute
            res.events.append((minute, "detected; a person starts the rollback"))
    res.decision = "kept"
    return res


def _burn(c: Counts, signal: str, target: float):
    from .analysis import burn
    return burn(c, signal, target)

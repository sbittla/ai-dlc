"""The citation check for an incident assistant's hypotheses (TODO 1: `check_citation` and `check_hypothesis`).

A hypothesis states a claim and cites telemetry. If it names a `cause` and an `effect` it is a cause hypothesis,
whatever `kind` the model gave it; otherwise it is an attribution. Each citation is an assertion:

- exists      the referenced event or alert exists (and was visible at the time).
- rises       mean(ref over window) >= factor x mean(ref over the checker's baseline); factor at least 3.
- precedes    the cause began no later than the effect's onset. The cause's time is the event's or alert's time,
              or, for a metric, its onset. An onset is the first minute after the checker's baseline window where
              the series reaches ONSET_FACTOR x its baseline mean (`Store.onset`).
- dominates   mean(ref over window) >= share: the cause's component takes most of the effect's resource. This is
              the mechanism: timing alone never makes a cause.

The checker, not the model, owns the baseline window (`Store.baseline`) and the map from each cause to the
component that would carry its mechanism (`Store.mechanism`). A citation must be about the hypothesis's own cause
and effect: `rises` and `precedes` cite the cause, `precedes` names the effect, and `dominates` cites the cause's
mechanism. A citation about anything else is `unbound` and supports nothing.

A verdict is `supported`, `unsupported` or `contradicted` (ADR-039). Only a supported hypothesis may justify an
action (`remediate.Gate.request` enforces it). An unsupported hypothesis may still be true.
"""

from __future__ import annotations

from dataclasses import dataclass

from .store import Store, minute_after

HOLDS, FAILS, UNRESOLVED, UNBOUND = "holds", "fails", "unresolved", "unbound"
ONSET_FACTOR = 5
MIN_RISE = 3


@dataclass(frozen=True)
class Verdict:
    hypothesis: str
    status: str            # supported, unsupported, contradicted
    results: tuple         # one of holds, fails, unresolved, unbound per citation, in order
    reason: str


def _known(store: Store, ref: str) -> bool:
    if ref.startswith(("metric:", "share:")):
        return ref in store.series
    if ref.startswith("event:"):
        return store.event(ref) is not None
    if ref.startswith("alert:"):
        return store.alert(ref) is not None
    return False


def is_cause(h: dict) -> bool:
    """A hypothesis that names a cause and an effect is a cause hypothesis, whatever its `kind` says."""
    return bool(h.get("cause")) and bool(h.get("effect"))


def bound(c: dict, h: dict, store: Store) -> bool:
    """Is citation `c` about this hypothesis's own cause, effect and mechanism? (provided)"""
    if not is_cause(h) or c["assert"] == "exists":
        return True
    if c["assert"] == "rises":
        return c["ref"] == h["cause"]
    if c["assert"] == "precedes":
        return c["ref"] == h["cause"] and c.get("effect") == h["effect"]
    if c["assert"] == "dominates":
        return c["ref"] == store.mechanism(h["cause"])
    return False


def check_citation(c: dict, store: Store) -> str:
    """TODO 1a. Evaluate one citation against `store` (which already hides anything after its as_of).

    Return UNRESOLVED when the reference is unknown (see `_known`) or a window has no visible data. Otherwise
    return HOLDS or FAILS. Use the checker's baseline, `store.baseline`, never one the citation names. `rises`
    holds when the window's mean is at least max(c["factor"], MIN_RISE) x the baseline mean. `precedes` holds
    when the cause's time (an event's or alert's time, or a metric's onset) is no later than the effect's onset,
    both onsets taken with `store.onset(ref, store.baseline, ONSET_FACTOR)`; an unknown time is UNRESOLVED.
    """
    raise NotImplementedError("TODO 1a: check_citation")


def counter_evidence(h: dict, store: Store) -> str | None:
    """The checker's own queries against a cause hypothesis (provided). A reason if telemetry contradicts it.

    1. The effect began before the cause (an event or alert): the cause cannot explain it.
    2. The cause was a change that has been undone, and the effect is still elevated 5 to 15 minutes later.
    Both use the checker's baseline and ONSET_FACTOR, not anything the hypothesis chose.
    """
    if not is_cause(h) or not h["effect"].startswith("metric:"):
        return None
    cause_at = store.time_of(h["cause"])
    if cause_at:
        onset = store.onset(h["effect"], store.baseline, ONSET_FACTOR)
        if onset is not None and onset < cause_at:
            return f"{h['effect']} began at {onset:%H:%M}, before {h['cause']} at {cause_at:%H:%M}"
    removed = store.removal_of(h["cause"]) if h["cause"].startswith("event:") else None
    if removed:
        a, b = minute_after(removed, 5), minute_after(removed, 15)
        later = store.mean(h["effect"], f"{a:%H:%M}", f"{b:%H:%M}")
        base = store.mean(h["effect"], *store.baseline)
        if later is not None and base is not None and later >= ONSET_FACTOR * base:
            return f"{h['effect']} stayed {later / max(base, 1e-9):.0f}x its baseline after {h['cause']} was " \
                   f"undone at {removed:%H:%M}"
    return None


def check_hypothesis(h: dict, store: Store) -> Verdict:
    """TODO 1b. The verdict for one hypothesis, in this order:

    1. No citations: unsupported, reason "no citations".
    2. `counter_evidence` gives a reason: contradicted, with that reason.
    3. Each citation's result is UNBOUND if `bound` says it is not about this hypothesis, else `check_citation`.
       Any result other than HOLDS: unsupported, reason "citation <n> <result>" for the first (n from 1).
    4. A cause hypothesis (`is_cause`) with no `dominates` citation: unsupported, "no mechanism cited"; with no
       `precedes` or `rises` citation: unsupported, "no timing cited".
    5. Otherwise supported, reason "".
    `results` holds every citation's result, in order, whatever the verdict (empty for no citations).
    """
    raise NotImplementedError("TODO 1b: check_hypothesis")

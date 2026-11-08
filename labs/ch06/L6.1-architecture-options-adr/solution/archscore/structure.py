"""Structural facts about an option, computed from its components and flows (provided).

These are counts, not judgements: deployable units, process types, data
stores, trust boundaries, and the internal components that must all be up for
an escalation step to fire. `path_availability` is Equation 6.1 in the chapter:
the availability of components in series, assuming each fails independently.
"""

from __future__ import annotations

from .model import Option

MINUTES_PER_30_DAYS = 30 * 24 * 60


def deployables(option: Option) -> list[str]:
    return sorted({c.deployable for c in option.components if c.deployable})


def process_types(option: Option) -> int:
    return sum(1 for c in option.components if c.kind == "process")


def datastores(option: Option) -> int:
    return sum(1 for c in option.components if c.kind == "datastore")


def brokers(option: Option) -> int:
    return sum(1 for c in option.components if c.kind == "broker")


def boundary_ids(option: Option) -> list[str]:
    return sorted(option.boundaries)


def crossings(option: Option) -> int:
    """Flows that cross a trust boundary."""
    return sum(1 for f in option.flows if f.boundary)


def path_availability(option: Option, per_component: float = 0.999) -> tuple[int, float]:
    """(n, a**n): availability of the step path if each component has availability `a`, independently."""
    n = len(option.step_path)
    return n, per_component ** n


def unavailable_minutes(availability: float, minutes: int = MINUTES_PER_30_DAYS) -> float:
    return (1 - availability) * minutes


def metrics(option: Option, per_component: float = 0.999) -> dict:
    n, avail = path_availability(option, per_component)
    return {
        "deployable units": len(deployables(option)),
        "process types": process_types(option),
        "databases": datastores(option),
        "message brokers": brokers(option),
        "trust boundaries": len(option.boundaries),
        "flows crossing a boundary": crossings(option),
        "components a step needs": n,
        "step-path availability": avail,
        "step path down, minutes per 30 days": unavailable_minutes(avail),
    }

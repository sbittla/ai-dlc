"""A capacity plan for self-hosting Relay's triage model, against the managed API. TODO 4 is `capacity_plan`."""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import load
from .engine import Summary


@dataclass(frozen=True)
class Plan:
    precision: str
    engine: str
    max_rate_meeting_slo: float     # requests per second, the highest tested rate that met the SLO
    peak_rate: float                # Relay's outage peak, requests per second
    utilization_at_peak: float      # peak_rate / max_rate_meeting_slo
    replicas: int                   # accelerators needed for the peak, plus one spare
    selfhost_usd_month: float
    tickets_month: int
    api_usd_month: float
    ratio: float                    # selfhost / api
    break_even_tickets_month: int | None  # smallest monthly volume at which self-hosting costs no more; None: never
    break_even_replicas: int | None       # accelerators (with the spare) needed at that volume
    usd_per_ticket_full_use: float        # one accelerator's monthly cost over the tickets it can serve in a month


def replicas_for(tickets_month: float, per_accelerator_tickets: float) -> int:
    """Accelerators for a monthly volume: enough for its peak, at the rate that meets the target, plus one spare."""
    return math.ceil(tickets_month / per_accelerator_tickets) + 1


def break_even(per_accelerator_tickets: float, accelerator_usd_month: float, api_usd_per_ticket: float,
               max_accelerators: int = 10_000) -> tuple[int | None, int | None]:
    """TODO 4b. The smallest whole monthly volume at which self-hosting, with replicas that grow with the volume, costs no
    more than the API, and the replicas it needs then. (None, None) if it never does: when one accelerator's
    monthly cost exceeds what the API charges for all the tickets it can serve, adding volume never catches up.
    """
    if accelerator_usd_month >= per_accelerator_tickets * api_usd_per_ticket:
        return None, None
    for active in range(1, max_accelerators + 1):
        low = math.floor((active - 1) * per_accelerator_tickets) + 1
        high = math.floor(active * per_accelerator_tickets)
        need = math.ceil((active + 1) * accelerator_usd_month / api_usd_per_ticket)
        tickets = max(low, need)
        if tickets <= high:
            return tickets, active + 1
    return None, None


def capacity_plan(sweep: list[Summary], engine: str, precision: str, volume: dict | None = None,
                  serving: dict | None = None) -> Plan:
    """TODO 4a. Size the self-hosted option for `engine` and `precision` and compare it with the managed API.

    - max_rate_meeting_slo: the highest rate among the sweep's rows for this engine and precision with
      meets_slo True (0.0 if none).
    - peak_rate: volume's outage_peak_per_minute / 60, rounded to 3 places.
    - utilization_at_peak: peak_rate / max_rate_meeting_slo, rounded to 3 places.
    - replicas: ceil(peak_rate / max_rate_meeting_slo) + 1 (one spare, so a failure or a deploy leaves capacity).
    - selfhost_usd_month: replicas x hours_per_month x the accelerator's price per hour, rounded to 2 places.
    - tickets_month: round(tickets_in_replay / replay_days x hours_per_month / 24).
    - api_usd_month: tickets_month x api_usd_per_suggestion, rounded to 2 places.
    - ratio: selfhost_usd_month / api_usd_month, rounded to 1 place.
    - break_even_tickets_month, break_even_replicas: `break_even(...)` with one accelerator's capacity in tickets a
      month (max_rate_meeting_slo / (outage_peak_per_minute / 60) x tickets_month, unrounded), one accelerator's
      monthly cost (hours_per_month x price) and the API's price per ticket. Replicas grow with volume, so an
      option whose accelerator costs more than the API would charge for the tickets it can serve never breaks even.
    - usd_per_ticket_full_use: one accelerator's monthly cost / its capacity in tickets a month, rounded to 6 places.
    """
    volume = volume or load("relay-volume.json")
    serving = serving or load("serving.json")
    ok = [s.rate for s in sweep if s.engine == engine and s.precision == precision and s.meets_slo]
    best = max(ok) if ok else 0.0
    peak = round(volume["outage_peak_per_minute"] / 60, 3)
    replicas = math.ceil(peak / best) + 1 if best else 0
    selfhost = round(replicas * volume["hours_per_month"] * serving["accelerator"]["price_usd_per_hour"], 2)
    tickets = round(volume["tickets_in_replay"] / volume["replay_days"] * volume["hours_per_month"] / 24)
    api = round(tickets * volume["api_usd_per_suggestion"], 2)
    per_accelerator = best / (volume["outage_peak_per_minute"] / 60) * tickets if best else 0.0
    accelerator_month = volume["hours_per_month"] * serving["accelerator"]["price_usd_per_hour"]
    even, even_replicas = (break_even(per_accelerator, accelerator_month, volume["api_usd_per_suggestion"])
                           if best else (None, None))
    return Plan(precision, engine, best, peak, round(peak / best, 3) if best else 0.0, replicas, selfhost, tickets,
                api, round(selfhost / api, 1), even, even_replicas,
                round(accelerator_month / per_accelerator, 6) if per_accelerator else 0.0)

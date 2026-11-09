"""Per-fault incident measures from a game day's timeline (TODO 2: `fault_measures`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Entry:
    at: datetime
    kind: str   # alert, page, ack, hypothesis, request, refusal, approval, action, automation, fault
    what: str   # rule ID, action name, hypothesis ID ...
    detail: str = ""


def minutes(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 60, 1)


def fault_measures(entries: list[Entry], plan: dict) -> dict[str, dict]:
    """TODO 2. For each fault in plan["faults"] (in order), a dict with:

    - "first_alert": the rule of the earliest `alert` entry whose `what` is in plan["alerts"][fault], or None;
    - "detect_min": minutes from the fault's start to that alert;
    - "first_page": the rule of the earliest `page` entry for any of the fault's rules, or None;
    - "ack_min": minutes from that page to the earliest `ack` entry for any of the fault's rules at or after it,
      or None;
    - "mitigate_min": minutes from the fault's start to the earliest `action` or `automation` entry whose
      `what` is plan["mitigations"][fault], or None.
    Times in plan are ISO strings ("2027-02-18T14:10:00Z"); use `minutes`, which rounds to 0.1.
    """
    raise NotImplementedError("TODO 2: fault_measures")

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
    out = {}
    for f in plan["faults"]:
        start = datetime.strptime(f["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=entries[0].at.tzinfo)
        rules = set(plan["alerts"][f["id"]])
        alerts = sorted((e for e in entries if e.kind == "alert" and e.what in rules), key=lambda e: e.at)
        first = alerts[0] if alerts else None
        pages = sorted((e for e in entries if e.kind == "page" and e.what in rules), key=lambda e: e.at)
        page = pages[0] if pages else None
        acks = sorted((e for e in entries if e.kind == "ack" and e.what in rules and page and e.at >= page.at),
                      key=lambda e: e.at)
        mit = sorted((e for e in entries if e.kind in ("action", "automation") and
                      e.what == plan["mitigations"][f["id"]]), key=lambda e: e.at)
        out[f["id"]] = {"first_alert": first.what if first else None,
                        "detect_min": minutes(start, first.at) if first else None,
                        "first_page": page.what if page else None,
                        "ack_min": minutes(page.at, acks[0].at) if acks else None,
                        "mitigate_min": minutes(start, mit[0].at) if mit else None}
    return out

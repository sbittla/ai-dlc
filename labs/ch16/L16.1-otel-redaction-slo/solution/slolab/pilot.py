"""Runtime evidence from January's escalation pilot: ESC-AC30 per week (TODO 6) and D7's flood-cap review.

ESC-AC30: in a week of escalation logs, at least 95% of steps fire within 60 seconds of their due time.
D7: the flood cap of 20 escalation emails per target per hour, to be reviewed with the pilot's first month,
including the open question of whether P1 escalations should be exempt.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone


def parse(text: str) -> datetime:
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in text else "%Y-%m-%dT%H:%M:%SZ"
    return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)


def weekly_step_delays(rows: list[dict], start: datetime, within_s: float = 60.0) -> list[dict]:
    """TODO 6. One dict per week from `start`, in order: {"week", "steps", "on_time", "share", "worst_s", "passed"}.

    Week n covers [start + 7n days, start + 7(n + 1) days) by `due_at`; "week" is n + 1. A step is on time when
    fired_at - due_at is at most `within_s` seconds. "share" is on_time / steps rounded to 4 places, "worst_s"
    the largest delay rounded to 1 place, and "passed" is share >= 0.95 (ESC-AC30). Skip weeks with no steps.
    """
    weeks: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        due = parse(r["due_at"])
        n = int((due - start).total_seconds() // (7 * 86400))
        weeks[n].append((parse(r["fired_at"]) - due).total_seconds())
    out = []
    for n in sorted(weeks):
        delays = weeks[n]
        on_time = sum(1 for d in delays if d <= within_s)
        share = round(on_time / len(delays), 4)
        out.append({"week": n + 1, "steps": len(delays), "on_time": on_time, "share": share,
                    "worst_s": round(max(delays), 1), "passed": share >= 0.95})
    return out


def flood_cap_review(rows: list[dict]) -> dict:
    """The evidence for D7's review (provided): what the cap held, and what P1 exemption would have changed."""
    held = Counter(r["priority"] for r in rows if r["email"] == "held")
    per_hour: Counter = Counter()
    p1_per_hour: Counter = Counter()
    for r in rows:
        hour = parse(r["fired_at"]).strftime("%Y-%m-%dT%H")
        per_hour[(r["target"], hour)] += 1
        if r["priority"] == "P1":
            p1_per_hour[(r["target"], hour)] += 1
    over = sorted(k for k, v in per_hour.items() if v > 20)
    bursts = []
    for target, hour in over:  # every step for that target that hour: how many, how long, which priorities
        rows_h = [r for r in rows if r["target"] == target and parse(r["fired_at"]).strftime("%Y-%m-%dT%H") == hour]
        times = sorted(parse(r["fired_at"]) for r in rows_h)
        acks = sorted(parse(r["acknowledged_at"]) for r in rows_h if r["acknowledged_at"])
        bursts.append({"target": target, "hour": hour, "steps": len(rows_h),
                       "minutes": round((times[-1] - times[0]).total_seconds() / 60),
                       "priorities": dict(sorted(Counter(r["priority"] for r in rows_h).items())),
                       "first_ack": acks[0].strftime("%H:%M:%S") if acks else None})
    held_p1 = [r for r in rows if r["email"] == "held" and r["priority"] == "P1"]
    late_p1 = []
    for r in held_p1:
        ack = parse(r["acknowledged_at"]) if r["acknowledged_at"] else None
        if ack is None or ack - parse(r["fired_at"]) > timedelta(minutes=10):
            late_p1.append(r)
    p1 = [r for r in rows if r["priority"] == "P1"]
    acked_10 = sum(1 for r in p1 if r["acknowledged_at"] and parse(r["acknowledged_at"]) - parse(r["fired_at"])
                   <= timedelta(minutes=10))
    return {"steps": len(rows), "emails": sum(1 for r in rows if r["email"] == "emailed"),
            "held": dict(sorted(held.items())), "target_hours_over_cap": [f"{t}@{h}" for t, h in over],
            "bursts": bursts,
            "held_p1": len(held_p1), "held_p1_unacknowledged_10min": len(late_p1),
            "held_p1_targets": sorted({r["target"] for r in held_p1}),
            "webhooks_for_held_p1": sum(1 for r in held_p1 if r["webhook"] == "delivered"),
            "max_p1_per_target_hour": max(p1_per_hour.values()),
            "max_p1_per_target_hour_outside_outage": max(v for (t, h), v in p1_per_hour.items()
                                                          if h != "2027-01-21T10"),
            "p1_steps": len(p1), "p1_acknowledged_within_10min": acked_10}

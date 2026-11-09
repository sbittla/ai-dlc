"""Generate Lab 17.1's traffic data (deterministic; run from the lab folder).

    python scripts/generate_data.py            # writes data/traffic/ and data/manifest.json
    python scripts/generate_data.py --out DIR  # writes the same files under DIR (the tests compare them)

The traffic is SYNTHETIC: one week (Monday 1 to Sunday 7 February 2027, UTC) of per-minute request counts for
the routes Relay's HTTP service serves in this snapshot, as its access log would count them. The shape was
CONFIGURED below: a weekday curve with a morning peak in European business hours and a second one in the US
afternoon, a busier Monday morning, a burst of task reads at the top of each working hour (scheduled syncs),
weekends at a quarter of weekday traffic, and on Wednesday 3 February at 14:00 an outage that brings 300 extra
support tickets in ten minutes. Counts vary around the curve by a uniform draw from a fixed seed, with no
floating-point library calls, so every platform writes identical files. Nothing here is measured.

data/measured/ is NOT generated. It holds load-test runs recorded on the author's machine with Relay's
tools/loadtest.py, and this script never writes it.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
SEED = 1702
DAYS = ("2027-02-01", "2027-02-02", "2027-02-03", "2027-02-04", "2027-02-05", "2027-02-06", "2027-02-07")
WEEKDAYS = 5
JOURNEYS = ("get_task", "get_escalation", "get_triage_job", "post_triage_job", "healthz")
# Requests per second at the weekday peak (factor 1.0) for each journey; healthz is a constant probe.
PEAK_RATE = {"get_task": 36.0, "get_escalation": 4.8, "get_triage_job": 2.4, "post_triage_job": 0.032}
HEALTHZ_PER_MIN = 60
# Weekday shape by UTC hour, relative to the busiest hour.
HOURLY = (0.10, 0.08, 0.07, 0.07, 0.08, 0.12, 0.25, 0.50, 0.85, 1.00, 0.95, 0.85,
          0.70, 0.80, 0.90, 0.95, 0.85, 0.70, 0.50, 0.35, 0.25, 0.18, 0.14, 0.12)
WEEKEND = 0.25
MONDAY_MORNING = 1.15          # hours 08-11 on Monday
TOP_OF_HOUR = 1.30             # get_task in minute 0 of hours 08-17 on weekdays
SPREAD = 0.08                  # counts vary uniformly within +-8% of the curve
OUTAGE = {"day": "2027-02-03", "hour": 14, "minutes": 10, "tickets": 300, "polls_per_ticket": 3, "poll_minutes": 20}
TOKENS = 40                    # distinct callers (user tokens) active in the peak hour


def counts() -> list[list[int]]:
    rng = random.Random(SEED)
    rows = []
    for d, day in enumerate(DAYS):
        for hour in range(24):
            for minute in range(60):
                factor = HOURLY[hour] * (WEEKEND if d >= WEEKDAYS else 1.0)
                if d == 0 and 8 <= hour <= 11:
                    factor *= MONDAY_MORNING
                row = []
                for j in JOURNEYS:
                    if j == "healthz":
                        row.append(HEALTHZ_PER_MIN)
                        continue
                    mean = PEAK_RATE[j] * 60 * factor
                    if j == "get_task" and d < WEEKDAYS and 8 <= hour <= 17 and minute == 0:
                        mean *= TOP_OF_HOUR
                    noisy = mean * (1 + SPREAD * (2 * rng.random() - 1))
                    whole = int(noisy)
                    row.append(whole + (1 if rng.random() < noisy - whole else 0))
                if day == OUTAGE["day"] and hour == OUTAGE["hour"]:
                    if minute < OUTAGE["minutes"]:
                        row[3] += OUTAGE["tickets"] // OUTAGE["minutes"]
                    if minute < OUTAGE["poll_minutes"]:
                        row[2] += OUTAGE["tickets"] * OUTAGE["polls_per_ticket"] // OUTAGE["poll_minutes"]
                rows.append([d * 1440 + hour * 60 + minute, *row])
    return rows


def write(out: Path) -> None:
    traffic = out / "traffic"
    traffic.mkdir(parents=True, exist_ok=True)
    lines = ["minute," + ",".join(JOURNEYS)] + [",".join(str(v) for v in r) for r in counts()]
    (traffic / "week-2027-02-01.csv").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    meta = {"GENERATED": "by scripts/generate_data.py; synthetic, configured traffic, not measured",
            "start_utc": "2027-02-01T00:00:00Z", "days": list(DAYS), "minute": "minutes since start_utc",
            "journeys": {"get_task": "GET /v1/projects/{pid}/tasks/{tid}",
                         "get_escalation": "GET /v1/projects/{pid}/tasks/{tid}/escalation",
                         "get_triage_job": "GET /v1/triage-jobs/{id}",
                         "post_triage_job": "POST /v1/triage-jobs (a support ticket queued for triage)",
                         "healthz": "GET /healthz (load-balancer probes)"},
            "tokens_at_peak": TOKENS, "outage": OUTAGE, "seed": SEED,
            "outage_note": ("SYNTHETIC: a scenario, not a recorded event. A 20-minute task-board outage on Wednesday "
                            "3 February 2027 at 14:00 UTC that floods support with tickets; scenario owner tomas.b "
                            "(support lead). Chapter 16's 2 February credential-stuffing attack hit the web sign-in, "
                            "which these routes do not include, so it is not in this week.")}
    (traffic / "meta.json").write_bytes((json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    manifest = {"GENERATED": "by scripts/generate_data.py", "files": ["traffic/meta.json",
                                                                      "traffic/week-2027-02-01.csv"],
                "not_generated": "measured/ holds load-test runs recorded with relay-repo/tools/loadtest.py"}
    (out / "manifest.json").write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(LAB / "data"))
    args = ap.parse_args()
    write(Path(args.out))
    print(f"wrote traffic data to {args.out}")


if __name__ == "__main__":
    main()

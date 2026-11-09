"""Loaders for Lab 16.1's generated data (provided)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import DATA


def minute_index(start: datetime, text: str) -> int:
    t = datetime.strptime(text, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    return int((t - start).total_seconds() // 60)


def traffic(path: Path = DATA / "traffic" / "api-minutes.csv"):
    """(minutes, totals, errors, slow) as parallel lists, one entry per minute."""
    minutes, totals, errors, slow = [], [], [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.startswith("minute"):
            continue
        m, t, e, s = line.split(",")
        minutes.append(m)
        totals.append(int(t))
        errors.append(int(e))
        slow.append(int(s))
    return minutes, totals, errors, slow


def manifest(path: Path = DATA / "traffic" / "manifest.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def start_of(doc: dict) -> datetime:
    return datetime.strptime(doc["start"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def probes() -> list[dict]:
    return jsonl(DATA / "redaction" / "probes.jsonl")


def pilot() -> list[dict]:
    return jsonl(DATA / "pilot" / "escalations-2027-01.jsonl")


def quality_days(path: Path = DATA / "traffic" / "triage-quality-days.csv") -> list[tuple[str, int, int]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.startswith("day"):
            continue
        d, k, n = line.split(",")
        rows.append((d, int(k), int(n)))
    return rows


def journal() -> dict:
    return json.loads((DATA / "agents" / "journal.json").read_text(encoding="utf-8"))

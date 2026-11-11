"""What remains: the book's open items, as recorded, seen from the capstone.

`data/open-items.json` gathers the open items Chapters 4 to 20 handed on, each with the owner and the date the
book recorded, or null where the book recorded none. Nothing here invents an owner or a date. An item whose
date has passed is reported as "date passed, no completion recorded": the book records no completion, which
is not the same as knowing it was not done.
"""

from __future__ import annotations

from collections import Counter

from . import DATA, load_json


def items() -> list[dict]:
    return load_json(DATA / "open-items.json")["items"]


def status(item: dict, as_of: str) -> str:
    if not item.get("due"):
        return "no date recorded"
    return "date passed, no completion recorded" if item["due"] < as_of else "due later"


def view(as_of: str, track: str | None = None) -> dict:
    rows = [dict(i, status=status(i, as_of)) for i in items() if track is None or track in i["tracks"]]
    return {"as_of": as_of, "track": track, "rows": rows,
            "by_status": dict(Counter(r["status"] for r in rows)),
            "no_owner": sum(1 for r in rows if not r.get("owner")),
            "by_track": {t: sum(1 for r in rows if t in r["tracks"]) for t in "ABCD"}}

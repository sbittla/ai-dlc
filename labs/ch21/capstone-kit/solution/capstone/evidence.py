"""The evidence-pack checker (TODO 1 in starter/): every required item exists, is well formed and traces to its
sources.

A pack is a folder with a manifest, `pack.json`, that lists the team, its members and their contribution
statements, the acceptance criteria with the items that evidence them, every evidence item, and the open items.
An item names a file and the sources it was produced from, by reference: `pack:<path>` inside the pack, or
`<root>:<path>` under one of the pack's named roots (Relay's canonical tree, the labs folder, or a team's own
repository). A reference may not climb out of its root.

Codes (block = the pack is not complete; warn = reported, not blocking):

    EV001 block  a required kind of evidence has no item
    EV002 block  an item's file does not resolve
    EV003 block  an item has no recorded SHA-256, or its file no longer matches it
    EV004 block  an item is malformed for its kind (kinds.py), or its kind does not fit its requirement
    EV005 block  an item has no sources, or a source does not resolve or no longer matches its hash
    EV006 block  an acceptance criterion has no item that is present and free of blocking findings
    EV007 block  an item's label is not verified, modelled, deployed or open; "deployed" has no record; or
                 "open" has no owner or due date. An open item is a promise, not evidence: it never satisfies a
                 requirement or a criterion
    EV008 block  an item is evidence for another release than the one the pack defends; or a version-bound item
                 (kinds.VERSION_BOUND) does not record its release, in the manifest and in the file itself
    EV009 warn   an open item has no owner or no date; or its date has passed with no completion recorded
    EV010 block  contribution statements: a member without a statement or without owned items, or an item
                 or pull request whose owner or author is not a member
    EV011 block  an item is well formed and records a failing result (a gate that fails, "not ready", ...)
    EV012 block  an item carries a field that could hold attack text
    EV013 warn   an item rests on generated records rather than observations (for example deployment records
                 that stand in for checks of a production environment the evidence cannot reach)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import DATA, LABELS, REPO, Finding, load_json, sha256_file
from .kinds import NOTES, VALIDATORS, VERSION_BOUND, file_release


@dataclass
class Result:
    pack: dict
    findings: list[Finding] = field(default_factory=list)
    item_ok: dict[str, bool] = field(default_factory=dict)
    requirement_state: dict[str, str] = field(default_factory=dict)   # ok, blocked or missing

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]

    @property
    def complete(self) -> bool:
        return not self.blocking


def tracks() -> dict:
    return load_json(DATA / "tracks.json")


def resolver(pack: dict, pack_dir: Path):
    """A function from a reference to a file Path, or None if it does not resolve or climbs out of its root."""
    roots = {"pack": Path(pack_dir)}
    for name, where in pack.get("roots", {}).items():
        p = Path(where)
        roots[name] = p if p.is_absolute() else REPO / p

    def resolve(ref: str) -> Path | None:
        root, sep, rel = str(ref).partition(":")
        if not sep or root not in roots or not rel:
            return None
        parts = PurePosixPath(rel).parts
        if rel.startswith("/") or ".." in parts:
            return None
        path = roots[root].joinpath(*parts)
        return path if path.is_file() else None
    return resolve


def trace_sources(item: dict, resolve) -> list[str]:
    """Problems with an item's sources (EV005): none listed; a reference that does not resolve; a recorded hash
    that no longer matches. Each source is {"ref": ..., "sha256": optional}."""
    sources = item.get("sources") or []
    if not sources:
        return ["no sources: evidence must say what it was produced from"]
    problems = []
    for s in sources:
        path = resolve(s.get("ref", ""))
        if path is None:
            problems.append(f"source {s.get('ref')!r} does not resolve")
        elif s.get("sha256") and sha256_file(path) != s["sha256"]:
            problems.append(f"source {s['ref']} changed since the item was produced")
    return problems


def check(pack_dir: Path) -> Result:
    pack_dir = Path(pack_dir)
    pack = load_json(pack_dir / "pack.json")
    spec = tracks()["tracks"][pack["track"]]
    reqs = {r["id"]: r for r in spec["requirements"]}
    resolve = resolver(pack, pack_dir)
    res = Result(pack)
    add = res.findings.append
    items = pack.get("items", [])
    item_ids = {i["id"] for i in items}
    members = {m["id"] for m in pack.get("members", [])}

    for item in items:
        iid = item["id"]
        before = len(res.findings)
        label = item.get("label")
        if label not in LABELS:
            add(Finding("EV007", "block", iid, f"label {label!r} is not one of {', '.join(LABELS)}"))
        elif label == "deployed" and resolve(item.get("deployment", "")) is None:
            add(Finding("EV007", "block", iid, "labelled deployed with no deployment record"))
        elif label == "open" and not (item.get("due") and item.get("owner")):
            add(Finding("EV007", "block", iid, "labelled open with no owner or no due date"))
        if label == "open":            # a dated promise: nothing to hash or validate yet
            res.item_ok[iid] = False
            continue
        req = reqs.get(item.get("requirement"))
        if req is None:
            add(Finding("EV004", "block", iid, f"requirement {item.get('requirement')!r} is not in track "
                                               f"{pack['track']}"))
        elif item.get("kind") not in req["kinds"]:
            add(Finding("EV004", "block", iid, f"kind {item.get('kind')!r} does not fit {req['id']}"))
        if item.get("release") and item["release"] != pack["release"]:
            add(Finding("EV008", "block", iid, f"evidence for {item['release']}, the pack defends "
                                               f"{pack['release']}"))
        if item.get("kind") in VERSION_BOUND and not item.get("release"):
            add(Finding("EV008", "block", iid, "version-bound evidence with no release in the manifest"))
        if item.get("owner") and members and item["owner"] not in members:
            add(Finding("EV010", "block", iid, f"owner {item['owner']} is not a member of the team"))
        for problem in trace_sources(item, resolve):
            add(Finding("EV005", "block", iid, problem))
        path = resolve(item.get("file", ""))
        if path is None:
            add(Finding("EV002", "block", iid, f"file {item.get('file')!r} does not resolve"))
        else:
            if not item.get("sha256"):
                add(Finding("EV003", "block", iid, "no SHA-256 recorded"))
            elif sha256_file(path) != item["sha256"]:
                add(Finding("EV003", "block", iid, "file changed since its hash was recorded"))
            if item.get("kind") in VERSION_BOUND:
                try:
                    inside = file_release(item["kind"], path)
                except (ValueError, AttributeError):
                    inside = None
                if not inside:
                    add(Finding("EV008", "block", iid, "the file does not say which release it is evidence for"))
                elif item.get("release") and inside != item["release"]:
                    add(Finding("EV008", "block", iid, f"the file says release {inside}, the manifest "
                                                       f"{item['release']}"))
            if req is not None and item.get("kind") in VALIDATORS:
                ctx = {"track": pack["track"], "team": pack.get("team"), "as_of": pack["as_of"],
                       "resolve": resolve, "item_ids": item_ids, "requirement": req,
                       "members": sorted(members)}
                try:
                    bad, failing, content = VALIDATORS[item["kind"]](path, item, ctx)
                except (ValueError, KeyError, TypeError, AttributeError, IndexError, SyntaxError) as exc:
                    bad, failing, content = [f"cannot be read as {item['kind']}: {exc!r}"], [], []
                for m in bad:
                    add(Finding("EV004", "block", iid, m))
                for m in failing:
                    add(Finding("EV011", "block", iid, m))
                for m in content:
                    add(Finding("EV012", "block", iid, m))
                if not bad and item["kind"] in NOTES:
                    for m in NOTES[item["kind"]](path, item, ctx):
                        add(Finding("EV013", "warn", iid, m))
        res.item_ok[iid] = not any(f.severity == "block" for f in res.findings[before:]) and label != "open"

    for rid, req in reqs.items():
        mine = [i["id"] for i in items if i.get("requirement") == rid and i.get("label") != "open"]
        promised = [i for i in items if i.get("requirement") == rid and i.get("label") == "open"]
        if not mine:
            res.requirement_state[rid] = "missing"
            if not req.get("optional"):
                due = f" (open: {promised[0]['owner']}, due {promised[0].get('due')})" if promised else ""
                add(Finding("EV001", "block", rid, f"no item for '{req['title']}'{due}"))
        else:
            res.requirement_state[rid] = "ok" if all(res.item_ok[i] for i in mine) else "blocked"

    for crit in pack.get("criteria", []):
        usable = [e for e in crit.get("evidence", []) if res.item_ok.get(e)]
        if not usable:
            cited = ", ".join(crit.get("evidence", [])) or "none"
            add(Finding("EV006", "block", crit["id"], f"no usable evidence (cites {cited})"))

    if not pack.get("members"):
        add(Finding("EV010", "block", "team", "no members and no contribution statements"))
    owned = Counter(i.get("owner") for i in items)
    for m in pack.get("members", []):
        if resolve(m.get("statement", "")) is None:
            add(Finding("EV010", "block", m["id"], "no contribution statement"))
        if not owned.get(m["id"]):
            add(Finding("EV010", "block", m["id"], "owns no item"))
    for pr in pack.get("prs", []):
        for a in pr.get("authors", []):
            if a not in members:
                add(Finding("EV010", "block", pr["id"], f"author {a} is not a member of the team"))

    for o in pack.get("open_items", []):
        if not o.get("owner") or not (o.get("due") or o.get("due_condition")):
            add(Finding("EV009", "warn", o["id"], f"no {'owner' if not o.get('owner') else 'date'}: {o['what']}"))
        elif o.get("due") and o["due"] < pack["as_of"]:
            add(Finding("EV009", "warn", o["id"], f"due {o['due']} ({o['owner']}), no completion recorded: "
                                                  f"{o['what']}"))
    return res


def summary(res: Result) -> dict:
    pack = res.pack
    labels = Counter(i.get("label") for i in pack.get("items", []))
    states = Counter(res.requirement_state.values())
    codes = Counter(f.code for f in res.blocking)
    crit = pack.get("criteria", [])
    crit_bad = {f.where for f in res.findings if f.code == "EV006"}
    return {"items": len(pack.get("items", [])), "labels": dict(labels),
            "requirements": len(res.requirement_state), "ok": states.get("ok", 0),
            "blocked": states.get("blocked", 0), "missing": states.get("missing", 0),
            "criteria": len(crit), "criteria_ok": len(crit) - len(crit_bad),
            "blocking": len(res.blocking), "warnings": len(res.findings) - len(res.blocking),
            "codes": dict(sorted(codes.items())), "complete": res.complete}

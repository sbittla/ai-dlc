"""The defense draw (TODO 5 in starter/): for each member, a part of the work they did not write, chosen at random
but reproducibly from the panel's seed.

Commit, freeze, reveal. At the red-team exchange the panel publishes the SHA-256 of a seed it keeps secret (the
commitment). At the readiness review the team freezes its contribution statements: the parts of the work, who
wrote each, and whether an agent helped; the freeze is the SHA-256 of their canonical JSON, recorded in the
review. At the defense the panel reveals the seed. The draw for member m is the part, among those m did not
write, with the smallest SHA-256 of "seed|freeze|m|part". Anyone can re-run it. The team froze without knowing
the seed, and the panel committed to the seed before it saw the frozen statements, so neither side can steer
a draw towards a part it chose.

    DF001  the statements changed after they were frozen (their hash differs from the readiness review's)
    DF002  a part names no author
    DF003  a part names an author who is not a member
    DF004  the revealed seed does not match the panel's commitment
    DF005  a part's authors are not the authors of the pull requests it names in the pack (authorship comes from
           the pack's record of pull requests, not from what a member says about themselves)
    DF006  a member's pool of parts they did not write is smaller than max(3, half the parts): a team cannot
           narrow a draw by having one member claim nearly everything
    DF007  the statements' members are not the pack's members, or a team's statements name no pack
    DF008  a pull request in the pack's record belongs to no part, so it could never be drawn; or the record
           itself is missing, unhashed or changed
    DF009  the part list has no instructor's approval, or a team member signed it (parts are only as fine as the
           team makes them); the kit can refuse a member, and the instructor confirms who actually approved

What remains possible: the pull-request record is the team's own export. The kit checks that it is unchanged
since its hash was recorded and that every part maps onto it; the instructor checks it against the code host.
A team could still record co-authors on pull requests a member barely touched. DF006 bounds how far that can
narrow a draw, and the panel can ask any member about any part in the question segment.
"""

from __future__ import annotations

import hashlib
import math

from . import Finding, canonical_sha256


def frozen_hash(statements: dict) -> str:
    return canonical_sha256({"members": statements["members"], "parts": statements["parts"]})


def min_pool(n_parts: int) -> int:
    return max(3, math.ceil(n_parts / 2))


def check(statements: dict, pack: dict | None = None, pack_dir=None) -> list[Finding]:
    out = []
    approved = statements.get("parts_approved") or {}
    if not (approved.get("by") and approved.get("date")):
        out.append(Finding("DF009", "block", "statements", "the part list has no instructor's approval"))
    elif approved["by"] in statements["members"]:
        out.append(Finding("DF009", "block", "statements", f"the part list was approved by {approved['by']}, a "
                                                         "member of the team, not the instructor"))
    if frozen_hash(statements) != statements.get("frozen_sha256"):
        out.append(Finding("DF001", "block", "statements", "changed after they were frozen"))
    members = set(statements["members"])
    for p in statements["parts"]:
        if not p.get("authors"):
            out.append(Finding("DF002", "block", p["id"], "no author"))
        for a in p.get("authors", []):
            if a not in members:
                out.append(Finding("DF003", "block", p["id"], f"author {a} is not a member"))
    if len(members) > 1:
        if pack is None:
            out.append(Finding("DF007", "block", "statements", "a team's statements must name its pack"))
        else:
            if members != {m["id"] for m in pack.get("members", [])}:
                out.append(Finding("DF007", "block", "statements", "members differ from the pack's members"))
            from .evidence import load_prs
            records, problems = load_prs(pack, pack_dir) if pack_dir is not None else ([], ["no pack folder"])
            for m in problems:
                out.append(Finding("DF008", "block", "prs_record", m))
            prs = {pr["id"]: set(pr.get("authors", [])) for pr in records}
            covered = {x for p in statements["parts"] for x in (p.get("prs") or [])}
            for pr_id in prs:
                if pr_id not in covered:
                    out.append(Finding("DF008", "block", pr_id, "belongs to no part, so it could never be drawn"))
            for p in statements["parts"]:
                named = p.get("prs") or []
                unknown = [x for x in named if x not in prs]
                derived = set().union(*(prs[x] for x in named if x in prs)) if named else set()
                if not named or unknown or derived != set(p.get("authors", [])):
                    out.append(Finding("DF005", "block", p["id"], f"authors {sorted(p.get('authors', []))} are "
                                       f"not the pack's authors of {named or 'no pull request'}"))
        need = min_pool(len(statements["parts"]))
        for m in sorted(members):
            pool = sum(1 for p in statements["parts"] if m not in p.get("authors", []))
            if pool < need:
                out.append(Finding("DF006", "block", m, f"{pool} parts to draw from; at least {need} needed"))
    return out


def _digest(seed: str, freeze: str, member: str, key: str) -> str:
    return hashlib.sha256(f"{seed}|{freeze}|{member}|{key}".encode("utf-8")).hexdigest()


def draw(statements: dict, seed: str, commitment: str, pack: dict | None = None, pack_dir=None) -> list[dict]:
    """One draw per member, in member order: {member, part, title, solo, questions}. Candidates are the parts the
    member did not write; a solo learner, who wrote everything, draws from all parts. The change request is
    the part's change_requests entry at index int(digest, 16) % len(...). `commitment` comes from the panel's own
    record, not from the team's statements; `pack` is the team's pack manifest (needed for a team, DF007)."""
    problems = check(statements, pack, pack_dir)
    if hashlib.sha256(seed.encode("utf-8")).hexdigest() != commitment:
        problems.append(Finding("DF004", "block", "seed", "does not match the panel's commitment"))
    if problems:
        raise ValueError("; ".join(f.line() for f in problems))
    freeze = statements["frozen_sha256"]
    out = []
    for m in statements["members"]:
        candidates = [p for p in statements["parts"] if m not in p["authors"]]
        solo = not candidates
        pool = statements["parts"] if solo else candidates
        part = min(pool, key=lambda p: _digest(seed, freeze, m, p["id"]))
        d = _digest(seed, freeze, m, part["id"])
        crs = part.get("change_requests") or ["a change the panel names at the defense"]
        out.append({"member": m, "part": part["id"], "title": part["title"], "solo": solo,
                    "authors": part["authors"], "ai_assisted": part.get("ai_assisted", False),
                    "questions": [f"Explain what {part['title']} does and why it is correct.",
                                  "What input or change would break it, and which test or check would catch it?",
                                  f"With an agent, make this change and verify it: {crs[int(d, 16) % len(crs)]}"]})
    return out


def draw_criteria(criteria: list[str], seed: str, freeze: str, k: int = 2) -> list[str]:
    """The k acceptance criteria for the evidence walk-through, drawn the same way."""
    return sorted(criteria, key=lambda c: _digest(seed, freeze, "criteria", c))[:k]

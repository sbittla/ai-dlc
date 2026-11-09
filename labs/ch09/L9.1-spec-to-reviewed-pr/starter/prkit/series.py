"""Relay 4.22.0's pull requests, measured from canonical 4.21.0 (provided).

`data/pr-plan.json` names each pull request's commits and the files each
commit changed. This module measures every file's change from
`data/relay-4.21.0/` (the base) to a Relay repository (the reference, by
default), and turns the plan into records that `prcheck.check_pr` reads, in
the same shape as `data/incident-pr.json`.

Files are assigned whole: a file that two pull requests changed would appear
in the later one. In this series no file is changed twice, and
`unassigned` reports any changed file the plan forgot.
"""

from __future__ import annotations

import json
from pathlib import Path

from .diffs import FileChange, change

TREES = ("src", "tests", "specs", "docs")
FILES = ("AGENTS.md", ".github/CODEOWNERS", "pyproject.toml")


def tree_files(root: Path) -> dict[str, str]:
    out = {}
    for top in TREES:
        for p in sorted((root / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    for name in FILES:
        if (root / name).exists():
            out[name] = (root / name).read_text(encoding="utf-8")
    return out


def changes(base: Path, repo: Path) -> dict[str, FileChange]:
    old, new = tree_files(base), tree_files(repo)
    out = {}
    for path in sorted(set(old) | set(new)):
        c = change(path, old.get(path), new.get(path))
        if c is not None:
            out[path] = c
    return out


def load_plan(data: Path) -> dict:
    return json.loads((data / "pr-plan.json").read_text(encoding="utf-8"))


def records(data: Path, repo: Path) -> list[dict]:
    """The plan's pull requests as records, with every file's measured change.

    Each record carries `codeowners`: the CODEOWNERS text at the pull request's
    base, that is 4.21.0's until a pull request in the plan changes the file.
    """
    measured = changes(data / "relay-4.21.0", repo)
    owners = (data / "relay-4.21.0" / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    out = []
    for pr in load_plan(data)["prs"]:
        commits = []
        for commit in pr["commits"]:
            files = []
            for path in commit["files"]:
                c = measured.get(path)
                if c is None:
                    raise ValueError(f"{pr['id']}: {path} is not changed between 4.21.0 and this repository")
                files.append({"path": c.path, "status": c.status, "added": c.added, "removed": c.removed,
                              "added_lines": list(c.added_lines), "removed_lines": list(c.removed_lines)})
            commits.append({"author": commit["author"], "message": commit["message"], "files": files})
        out.append({"id": pr["id"], "title": pr["title"], "task": pr["task"], "merged": pr["merged"],
                    "opened_by": pr["opened_by"], "review": pr["review"], "description": pr["description"],
                    "commits": commits, "codeowners": owners})
        if any(f["path"] == ".github/CODEOWNERS" for c in commits for f in c["files"]):
            owners = (repo / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    return out


def grouped(data: Path, repo: Path) -> list[tuple[dict, int, int]]:
    """(group, files, changed lines) for the plan's groups, measured the same way."""
    measured = changes(data / "relay-4.21.0", repo)
    return [(g, len(g["files"]), sum(measured[p].changed for p in g["files"])) for g in load_plan(data)["groups"]]


def unassigned(data: Path, repo: Path) -> list[str]:
    """Changed files that no pull request and no group names; and files named twice, prefixed 'twice: '."""
    plan = load_plan(data)
    named = [p for pr in plan["prs"] for c in pr["commits"] for p in c["files"]]
    named += [p for g in plan["groups"] for p in g["files"]]
    twice = sorted({p for p in named if named.count(p) > 1})
    missing = sorted(set(changes(data / "relay-4.21.0", repo)) - set(named))
    return missing + [f"twice: {p}" for p in twice]

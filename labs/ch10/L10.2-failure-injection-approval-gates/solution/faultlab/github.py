"""Simulated GitHub, and the helper's `open_pull_request` handler.

GitHub refuses a second open pull request for the same head and base branches (it answers 422, "A pull
request already exists"). The simulation enforces nothing; it only counts what it is asked to do, so a
handler that creates blindly opens duplicates, and the drills can see it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SimGitHub:
    pulls: list[dict] = field(default_factory=list)
    creates: int = 0
    lookups: int = 0

    def find_open(self, branch: str) -> dict | None:
        self.lookups += 1
        return next((p for p in self.pulls if p["branch"] == branch and p["state"] == "open"), None)

    def create(self, branch: str, title: str, diff_sha256: str) -> dict:
        self.creates += 1
        pull = {"number": 5100 + len(self.pulls), "branch": branch, "title": title, "diff_sha256": diff_sha256,
                "state": "open", "draft": True}
        self.pulls.append(pull)
        return pull


def open_pull_request(github: SimGitHub, args: dict) -> dict:
    """Open a draft pull request from args["branch"], safely if it is called again after an unknown outcome.

    Look for an open pull request on the branch first (github.find_open). If there is one, return
    {"number": its number, "existing": True} without creating anything. Otherwise create one with
    github.create(branch, title, diff_sha256) and return {"number": its number, "existing": False}.
    This is what lets the contract declare `idempotent=True`.
    """
    existing = github.find_open(args["branch"])
    if existing is not None:
        return {"number": existing["number"], "existing": True}
    pull = github.create(args["branch"], args["title"], args["diff_sha256"])
    return {"number": pull["number"], "existing": False}

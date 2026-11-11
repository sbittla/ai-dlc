"""Dependency and vulnerability updates, from the mirror only (added in 4.31.0; ADR-054).

Chapter 13's rules stand: Relay installs only from its mirror, only wheels, every file pinned by hash, and a new
release is served only after a 7-day quarantine unless `@relay/security` releases a security fix early. The bot
proposes only versions the mirror serves on the day it runs (`Mirror.served`), with the mirror's hash.

What a version number does not tell the bot, `plan_update` does not assume:

- a **major** bump is never proposed; a person decides (`major_needs_a_person`);
- a **minor** bump of any package, and any bump of a security-sensitive package, needs a review by
  `@relay/security`, whatever the scanners say (`reviews` lists it);
- every plan needs the **pinned-defaults check**: the security-relevant defaults the application relies on,
  recorded in a reviewed file, compared with the new version's in the sandbox (`evidence.defaults_check`);
- a fix comes from the lowest served version at or above the advisory's fixed version, on the same minor line
  if there is one, so a security fix does not bring a feature release with it.

`apply` and `revert` rewrite one entry of a hash-locked requirements file and nothing else.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

from .semver import bump_kind, parse

_ENTRY = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^\s\\]+)\s*\\\s*\n"
                    r"\s*--hash=sha256:(?P<sha>[0-9a-f]{64})", re.MULTILINE)


def read_lock(text: str) -> dict[str, tuple[str, str]]:
    """{name: (version, sha256)} for every `name==version \\ --hash=sha256:...` entry."""
    return {m["name"].lower(): (m["version"], m["sha"]) for m in _ENTRY.finditer(text.replace("\r\n", "\n"))}


def locked_versions(text: str) -> dict[str, str]:
    return {k: v for k, (v, _) in read_lock(text).items()}


class Mirror:
    """The mirror's record (`supply-chain/mirror.json`'s shape) plus, per file, `released_on` and an optional
    `released_early_by`. A file with no `released_on` is treated as long served."""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.quarantine = int(data.get("new_release_quarantine_days", 7))
        self.projects = {p["name"].lower(): p for p in data.get("projects", [])}

    def files(self, name: str) -> list[dict]:
        return list(self.projects.get(name.lower(), {}).get("files", []))

    def served(self, name: str, today: str) -> list[dict]:
        day = _dt.date.fromisoformat(today)
        out = []
        for f in self.files(name):
            released = f.get("released_on")
            if released is None:
                out.append(f)
                continue
            on = _dt.date.fromisoformat(released)
            if on <= day and (f.get("released_early_by") or on + _dt.timedelta(days=self.quarantine) <= day):
                out.append(f)
        return out

    def sha(self, name: str, version: str) -> str:
        for f in self.files(name):
            if f["version"] == version:
                return f["sha256"]
        raise KeyError(f"{name}=={version} is not in the mirror")


@dataclass(frozen=True)
class UpdatePlan:
    package: str
    current: str
    target: str | None
    bump: str | None
    reviews: tuple[str, ...]
    refusal: str | None = None
    advisory: str | None = None


def plan_update(package: str, lock_text: str, mirror: Mirror, today: str, sensitive: frozenset[str],
                fixed: str | None = None, advisory: str | None = None) -> UpdatePlan:
    """The update to propose for `package`, or a plan whose `refusal` says why there is none."""
    name = package.lower()
    locked = locked_versions(lock_text)
    if name not in locked:
        return UpdatePlan(name, "", None, None, (), "not_locked", advisory)
    current = locked[name]
    cur = parse(current)

    def usable(files):
        vs = []
        for f in files:
            try:
                v = parse(f["version"])
            except ValueError:
                continue
            if not v.prerelease and v > cur and (fixed is None or v >= parse(fixed)):
                vs.append(v)
        return sorted(vs)

    served, every = usable(mirror.served(name, today)), usable(mirror.files(name))
    if not served:
        if every:
            return UpdatePlan(name, current, None, None, (), "in_quarantine", advisory)
        return UpdatePlan(name, current, None, None, (),
                          "no_fixed_version_served" if fixed else "up_to_date", advisory)
    same_minor = [v for v in served if (v.major, v.minor) == (cur.major, cur.minor)]
    same_major = [v for v in served if v.major == cur.major]
    if fixed is not None:  # the smallest change that fixes it
        choice = same_minor[0] if same_minor else (same_major[0] if same_major else served[0])
    else:                  # a refresh: the newest patch, else the newest minor
        choice = same_minor[-1] if same_minor else (same_major[-1] if same_major else served[-1])
    target = next(f["version"] for f in mirror.files(name) if parse(f["version"]) == choice)
    bump = bump_kind(current, target)
    if bump == "major":
        return UpdatePlan(name, current, target, bump, (), "major_needs_a_person", advisory)
    reviews = ["pinned-defaults", "tests", "scan"]
    if bump != "patch" or name in sensitive:
        reviews.append("security")
    return UpdatePlan(name, current, target, bump, tuple(reviews), None, advisory)


def _rewrite(lock_text: str, name: str, version: str, sha: str) -> str:
    text = lock_text.replace("\r\n", "\n")
    found = [m for m in _ENTRY.finditer(text) if m["name"].lower() == name]
    if len(found) != 1:
        raise ValueError(f"{name} must appear exactly once in the lock")
    m = found[0]
    new = f"{m['name']}=={version} \\\n    --hash=sha256:{sha}"
    return text[:m.start()] + new + text[m.end():]


def apply(lock_text: str, plan: UpdatePlan, mirror: Mirror) -> str:
    if plan.refusal or plan.target is None:
        raise ValueError(f"no update to apply: {plan.refusal}")
    return _rewrite(lock_text, plan.package, plan.target, mirror.sha(plan.package, plan.target))


def revert(lock_text: str, plan: UpdatePlan, mirror: Mirror) -> str:
    """The lock with `plan`'s package back at the version it had before (a rollback's change)."""
    locked = locked_versions(lock_text)
    if locked.get(plan.package) != plan.target:
        raise ValueError(f"{plan.package} is not at {plan.target}; nothing to revert")
    return _rewrite(lock_text, plan.package, plan.current, mirror.sha(plan.package, plan.current))

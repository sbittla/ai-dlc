"""Version numbers and what kind of change a bump claims to be (added in 4.31.0; ADR-054).

Semantic Versioning 2.0.0 asks a project to raise MINOR for backward-compatible features and MAJOR for anything
incompatible, and says that before 1.0.0 anything may change. That is a promise a maintainer makes, not a
property a tool can check: a minor release that changes a default is "compatible" to its maintainer and an
outage to its user. So `bump_kind` names what a bump *claims*, and Relay's maintenance policy never treats a
claim as evidence (ADR-054). Pre-1.0 bumps of the minor number count as major here, as SemVer allows.

Accepted forms: `X.Y.Z`, `X.Y` (read as `X.Y.0`, as for `packaging` 25.0) and a pre-release suffix after `-`,
`a`, `b` or `rc` (`2.5.0rc1`, `2.5.0-beta.1`). Anything else is refused with ValueError, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:(?:-|(?=a|b|rc))([0-9A-Za-z.]+))?$")
KINDS = ("none", "patch", "minor", "major", "downgrade", "prerelease")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: str = ""

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}" + (f"-{self.pre}" if self.pre else "")

    @property
    def prerelease(self) -> bool:
        return bool(self.pre)


def parse(text: str) -> Version:
    m = _VERSION.match(text.strip()) if isinstance(text, str) else None
    if m is None:
        raise ValueError(f"not a version this policy accepts: {text!r}")
    return Version(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), m.group(4) or "")


def bump_kind(old: str, new: str) -> str:
    """What the move from `old` to `new` claims to be: one of KINDS.

    A pre-release target is `prerelease` whatever the numbers say. Before 1.0.0 a change of the minor number is
    `major` and a change of the patch number is `minor`, because SemVer promises nothing there.
    """
    a, b = parse(old), parse(new)
    if b.prerelease:
        return "prerelease"
    key_a, key_b = (a.major, a.minor, a.patch), (b.major, b.minor, b.patch)
    if key_b == key_a:
        return "none"
    if key_b < key_a:
        return "downgrade"
    if b.major != a.major:
        return "major"
    if a.major == 0:
        return "major" if b.minor != a.minor else "minor"
    return "minor" if b.minor != a.minor else "patch"

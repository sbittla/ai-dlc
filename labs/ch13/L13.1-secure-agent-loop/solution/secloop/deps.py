"""The dependency gate: nothing enters except admitted projects from the mirror, pinned by hash (TODO 2 in starter/).

Rules (scanner "depgate", severity 9.0, always blocking, never suppressible):

    DEP001  the project is not admitted to the mirror (supply-chain/mirror.json), and not an internal name
    DEP002  the name is within two edits of an admitted or popular project, but is not it (possible typosquat)
    DEP003  an index other than the mirror is named or added (dependency confusion), or an internal name
            is requested at a version the mirror does not serve
    DEP004  the requirement is not pinned with == and a sha256 hash
    DEP005  the version is not served by the mirror, or the hash differs from the mirror's file
"""

from __future__ import annotations

import re

from .sarif import Finding

REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(==|>=|<=|~=|>|<)?\s*([^\s;]+)?")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})\b")
SEVERITY = 9.0


def normalize(name: str) -> str:
    """PEP 503: runs of -, _ and . are equal; case does not matter."""
    return re.sub(r"[-_.]+", "-", name).lower()


def edit_distance(a: str, b: str) -> int:
    """Optimal string alignment distance: insertions, deletions, substitutions and adjacent transpositions."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def public_note(name: str, public: dict) -> str:
    """How the public index fixture describes a name (provided)."""
    p = public["packages"].get(name)
    if p is None:
        return "not on the public index either: a name nobody has published (likely hallucinated)"
    kind = "wheels" if p["wheels"] else "source distribution only"
    repo = "a source repository" if p["source_repository"] else "no source repository"
    return f"on the public index since {p['first_published']}, {p['versions']} version(s), {kind}, {repo}"


def check_requirements(change: str, path: str, lines: list[str], policy: dict, mirror: dict,
                       public: dict) -> list[Finding]:
    """Check the requirement lines an agent change adds to a lock file.

    `policy` is supply-chain/mirror.json; `mirror` is the mirror's index (what it serves, with hashes);
    `public` is the public index fixture. Each finding has scanner "depgate", severity SEVERITY, the change,
    `path`, line = the 1-based position of the line in `lines`, fingerprint = "<rule>:<normalized name or
    option>", and a message. Rules per line, in this order:

    - An option line (starts with "-"): "--extra-index-url", "-f", "--find-links" or "--trusted-host" gives
      DEP003; "--index-url X" or "-i X" with X other than the policy's index_url gives DEP003. Others pass.
    - Otherwise parse the name (REQ) and normalize it. Internal names start with a policy internal prefix.
    - Not pinned (operator is not "==", or no --hash) gives DEP004.
    - A name that is neither admitted (normalized names in policy["projects"]) nor internal gives DEP001
      with public_note() in its message; if edit_distance to any admitted or popular project (public index
      entries with "popular": true) is 1 or 2, also DEP002 naming the closest such project (ties: the
      alphabetically first).
    - An internal name pinned to a version the mirror does not serve gives DEP003 (the request would only
      resolve from a public index).
    - An admitted name, pinned with a hash, whose version the mirror does not serve or whose hashes do not
      include the mirror's file hash, gives DEP005.
    """
    out: list[Finding] = []
    admitted = {normalize(p["name"]) for p in policy["projects"]}
    popular = {normalize(n) for n, p in public["packages"].items() if p.get("popular")}
    served = {normalize(n): {f["version"]: f["sha256"] for f in p["files"]} for n, p in mirror["projects"].items()}

    def add(rule, n, key, msg):
        out.append(Finding("depgate", rule, SEVERITY, change, path, n, f"{rule}:{key}", msg))

    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("-"):
            opt = line.split()[0].split("=")[0]
            if opt in ("--extra-index-url", "-f", "--find-links", "--trusted-host"):
                add("DEP003", n, opt, f"{opt} adds a source outside the mirror (dependency confusion)")
            elif opt in ("--index-url", "-i"):
                url = line.split(None, 1)[1] if " " in line else line.split("=", 1)[1]
                if url != policy["index_url"]:
                    add("DEP003", n, opt, f"index {url} is not the mirror")
            continue
        m = REQ.match(line)
        name = normalize(m[1])
        internal = any(name.startswith(p) for p in policy["internal_prefixes"])
        hashes = HASH.findall(line)
        pinned = m[2] == "==" and bool(hashes)
        if not pinned:
            add("DEP004", n, name, f"{m[1]} is not pinned with == and a sha256 hash")
        if name not in admitted and not internal:
            add("DEP001", n, name, f"{m[1]} is not admitted to the mirror; {public_note(name, public)}")
            near = sorted((edit_distance(name, k), k) for k in admitted | popular if k != name)
            if near and near[0][0] <= 2:
                add("DEP002", n, name, f"{m[1]} is {near[0][0]} edit(s) from {near[0][1]}: possible typosquat")
            continue
        if internal and m[2] == "==" and m[3] not in served.get(name, {}):
            add("DEP003", n, name, f"{m[1]}=={m[3]} is an internal name the mirror does not serve at this version; "
                f"it would resolve only from outside")
            continue
        if pinned and not internal and (m[3] not in served.get(name, {}) or served[name][m[3]] not in hashes):
            add("DEP005", n, name, f"{m[1]}=={m[3]}: version or hash differs from the mirror's file")
    return out

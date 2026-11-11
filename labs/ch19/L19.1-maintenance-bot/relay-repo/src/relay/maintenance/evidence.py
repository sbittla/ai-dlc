"""Evidence for a maintenance proposal, gathered in the sandbox and labelled honestly (added in 4.31.0; ADR-054).

A proposal leaves the bot with an evidence bundle, and the person who approves it approves the bundle's hash as
well as the diff's. Each item says what it claims and how it was obtained:

- `verified`: run here, on this change, in the sandbox (`relay.agentops.sandbox.run_code`): the reproduction
  before and after, the application's tests, the pinned-defaults check, the lock-against-mirror check;
- `modelled`: a record produced elsewhere and passed in, such as a scanner's report for this diff when the
  scanner did not run here; the bundle carries it and says so;
- `deployed`: an observation of the running system, such as a guard metric after release.

`missing` is never a pass. A bundle with a required item that is missing or failing blocks the proposal.

Code the bot did not write runs only in the sandbox: a reporter's reproduction, the package under test, the
application's tests. The sandbox's local layer is Chapter 18's tripwire, not a boundary; in CI it runs on an
ephemeral runner with no credentials, and in the cloud on ADR-050's runner (ADR-050).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from ..agentops.sandbox import SandboxPolicy, run_code
from .updates import Mirror, read_lock

STATUSES = ("verified", "modelled", "deployed", "missing")
RESULTS = ("pass", "fail", "refused", "error")


@dataclass(frozen=True)
class Check:
    name: str
    result: str          # pass, fail, refused, error
    detail: str
    refusals: tuple[str, ...] = ()


def sandbox_check(name: str, files: dict[str, str], script: str, policy: SandboxPolicy | None = None) -> Check:
    """Run `script` beside `files` in the sandbox. Exit 0 is a pass, 1 a fail; a refusal is never a pass."""
    r = run_code(script, files, policy or SandboxPolicy(timeout_s=60.0))
    tail = (r.stdout.strip().splitlines() or [""])[-1][:200]
    if r.refused:
        return Check(name, "refused", tail, tuple(str(x.get("reason", "")) for x in r.refusals[:5]))
    if r.status == "ok":
        return Check(name, "pass", tail)
    if r.status == "error" and r.exit_code == 1:
        return Check(name, "fail", tail or r.stderr.strip()[-200:])
    return Check(name, "error", f"{r.status}: {r.stderr.strip()[-160:]}")


@dataclass(frozen=True)
class Reproduction:
    outcome: str         # fixed, not_reproduced, not_fixed, refused, error
    before: Check
    after: Check | None


def reproduce(before: dict[str, str], after: dict[str, str] | None, test: str,
              policy: SandboxPolicy | None = None) -> Reproduction:
    """A reproduction is a test that states the safe behaviour: it must fail before the change and pass after.

    `not_reproduced` (it passes before) means the report is not confirmed on this code; the bot hands it to a
    person rather than "fixing" it.
    """
    b = sandbox_check("reproduction-before", before, test, policy)
    if b.result in ("refused", "error"):
        return Reproduction(b.result, b, None)
    if b.result == "pass":
        return Reproduction("not_reproduced", b, None)
    if after is None:
        return Reproduction("reproduced", b, None)
    a = sandbox_check("reproduction-after", after, test, policy)
    if a.result in ("refused", "error"):
        return Reproduction(a.result, b, a)
    return Reproduction("fixed" if a.result == "pass" else "not_fixed", b, a)


def defaults_script(module: str, pinned: dict[str, dict[str, object]]) -> str:
    """A check that the keyword defaults of `module`'s callables equal the reviewed, pinned values.

    `pinned` maps a callable's name to {parameter: default}. Any difference, a missing callable or a missing
    parameter fails, with one line per difference.
    """
    return "\n".join([
        "import inspect, json, sys",
        f"import {module} as m",
        f"pinned = json.loads({json.dumps(json.dumps(pinned, sort_keys=True))})",
        "diffs = []",
        "for fn, params in sorted(pinned.items()):",
        "    f = getattr(m, fn, None)",
        "    if f is None:",
        "        diffs.append(fn + ': missing'); continue",
        "    sig = inspect.signature(f).parameters",
        "    for p, want in sorted(params.items()):",
        "        got = sig[p].default if p in sig else '<missing>'",
        "        if got != want:",
        "            diffs.append(f'{fn}({p}): pinned {want!r}, now {got!r}')",
        "print('; '.join(diffs) if diffs else 'defaults unchanged')",
        "sys.exit(1 if diffs else 0)",
        ""])


def lock_matches_mirror(lock_text: str, mirror: Mirror) -> Check:
    """Every locked file's hash is the mirror's (Chapter 13's rule, checked here on the new lock)."""
    bad = []
    for name, (version, sha) in sorted(read_lock(lock_text).items()):
        try:
            if mirror.sha(name, version) != sha:
                bad.append(f"{name}=={version}: hash differs")
        except KeyError:
            bad.append(f"{name}=={version}: not in the mirror")
    return Check("lock-matches-mirror", "fail" if bad else "pass", "; ".join(bad) or "every entry matches")


@dataclass(frozen=True)
class Item:
    item_id: str
    claim: str
    status: str          # verified, modelled, deployed, missing
    result: str          # pass, fail, refused, error
    source: str
    required: bool = True


def item(item_id: str, claim: str, check: Check | None, status: str = "verified", source: str = "",
         required: bool = True) -> Item:
    if check is None:
        return Item(item_id, claim, "missing", "error", source or "-", required)
    if status not in STATUSES:
        raise ValueError(f"unknown evidence status {status!r}")
    return Item(item_id, claim, status, check.result, source or check.name, required)


@dataclass(frozen=True)
class Bundle:
    items: tuple[Item, ...]
    ran_at: float | None = None   # when the checks ran (seconds); part of the hash when set

    def blocking(self) -> list[str]:
        """Required items that are missing or did not pass, in order."""
        return [i.item_id for i in self.items if i.required and (i.status == "missing" or i.result != "pass")]

    def sha256(self) -> str:
        items = [asdict(i) for i in self.items]
        body = json.dumps(items if self.ran_at is None else {"items": items, "ran_at": self.ran_at}, sort_keys=True,
                          separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def table(self) -> list[str]:
        rows = ["| Evidence | Claim | Status | Result | Source |", "| --- | --- | --- | --- | --- |"]
        rows += [f"| {i.item_id} | {i.claim} | {i.status} | {i.result} | {i.source} |" for i in self.items]
        return rows

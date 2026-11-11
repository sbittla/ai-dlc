"""The maintenance bot's policy: task types, tiers, paths, approvers (added in 4.31.0; ADR-053, ADR-056).

The policy is data in `maintenance/policy.json`, owned by `@relay/security` and `@relay/platform-leads`, and the
bot's own path list puts that file out of its reach. Three rules are checked here, not left to the bot:

- **Self-modification.** No task type may write a protected path: the bot's instructions (`AGENTS.md`), its
  workflow and every other file under `.github/`, its registry entry (`governance/`), this policy, its own code
  and the runtime it runs on, the scanners and their configuration, and the tests that check the bot. Paths are
  compared case-folded. A task type marked `self_modification` is refused outright: supporting one needs a new
  ADR, a safety and security case approved under the pipeline guard, and a reviewed change to this loader.
- **Inputs are derived, not declared.** Whether a task type reads untrusted input follows from what starts it
  and what it reads (`TRUSTED_INPUT_TASK_TYPES`, in this module's code): only the table extension, started by the
  scheduler and reading a reviewed rules file, reads none. A policy that declares otherwise is refused.
- **Tiers (Chapter 12's cap and ADR-056).** T0 to T2 load as written. T3 or T4 for a task type that reads untrusted
  input needs an autonomy grant whose eligibility report records A4 as passed (coverage gate and live attack
  measurement); T4 needs every criterion passed. The grant names three files under `maintenance/eligibility/`:
  the report (with its SHA-256), the outcome log and the evidence file, and an as-of date. The loader recomputes
  the report from the log and the evidence with `autonomy.eligibility_report` and refuses a report that differs,
  so a hand-edited report fails. What it cannot check is whether the log and the evidence are true: they are files
  in a protected, guarded path, and their truth rests on the code host's review of the change, which the pipeline
  guard requires to have two approvals, one from `@relay/security` (PG002, PG003). For the same reason a grant
  that types its own verdict or approver names is refused: the loader cannot authenticate people.
  Relay's policy v1 grants none.
- **Approvers.** Every task type names at least one team; who may approve a proposal is computed from
  `.github/CODEOWNERS` for the paths the proposal touches (`approver_problem`). Team membership is declared in the
  policy and must match the code host's own settings (an open item, as for `governance/agents.json`).

Missing or unknown values fail closed: a task type with no `reads_untrusted` field is treated as reading
untrusted input, and a path that matches no CODEOWNERS rule has no owner, so nobody can approve it.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

TIERS = ("T0", "T1", "T2", "T3", "T4")


@dataclass(frozen=True)
class TaskType:
    name: str
    tier: str
    write_paths: tuple[str, ...]
    approval_teams: tuple[str, ...]
    reads_untrusted: bool
    security_review: bool
    guard_metric: str | None
    budget: dict
    self_modification: bool = False
    safety_case: str | None = None
    autonomy_grant: dict | None = None


@dataclass(frozen=True)
class Policy:
    name: str
    agent_id: str
    bot_owner: str
    protected_paths: tuple[str, ...]
    sensitive_packages: frozenset[str]
    teams: dict[str, frozenset[str]]
    task_types: dict[str, TaskType]
    safety_cases: dict[str, dict]

    def task(self, name: str) -> TaskType:
        return self.task_types[name]

    def protected(self, path: str) -> bool:
        """Compared case-folded, so `docs/ADR/x.md` is as protected as `docs/adr/x.md` on a case-insensitive disk."""
        folded = path.casefold() if isinstance(path, str) else path
        return any(_under(folded, p.casefold()) for p in self.protected_paths)

    def writable(self, task_type: str, path: str) -> bool:
        t = self.task_types.get(task_type)
        if t is None or path_problem(path) or self.protected(path):
            return False
        return any(_under(path, p) for p in t.write_paths)


def path_problem(path: str) -> str | None:
    """Why `path` is not a plain repository path, or None."""
    if not isinstance(path, str) or not path or path.startswith(("/", "\\")) or "\\" in path or ":" in path:
        return "not a relative repository path"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "path has an empty, '.' or '..' part"
    return None


def _under(path: str, rule: str) -> bool:
    """A rule ending in '/' is a folder; ending in '*' a prefix; anything else one exact file."""
    if rule.endswith("/"):
        return path.startswith(rule)
    if rule.endswith("*"):
        return path.startswith(rule[:-1])
    return path == rule


def _people_ok(approvals: list, policy_teams: dict, owner: str, people: set) -> list[str]:
    """Structural check of names recorded in a document (a safety case). Names in a file are not authenticated;
    the code host's review of the file is what binds them."""
    names = [a.get("by") for a in approvals or []]
    problems = []
    if len(set(names)) < 2:
        problems.append("needs two different approvers")
    if owner in names:
        problems.append("the bot's owner may not approve")
    if any(n not in people for n in names):
        problems.append("every approver must be a person")
    if not set(names) & set(policy_teams.get("@relay/security", ())):
        problems.append("needs an approver from @relay/security")
    return problems


ELIGIBILITY_DIR = "maintenance/eligibility/"
# Task types that read nothing an outsider writes: started by Relay's scheduler, reading only reviewed files.
# Everything else (issue forms, advisory feeds, third-party package code) is untrusted. A change here is a change
# to `src/relay/maintenance/`, a guarded path that needs `@relay/security`.
TRUSTED_INPUT_TASK_TYPES = frozenset({"table-extension"})


def reads_untrusted(task_type: str) -> bool:
    return task_type not in TRUSTED_INPUT_TASK_TYPES


def _read(root: Path, path: object, what: str) -> tuple[bytes | None, str | None]:
    if not isinstance(path, str) or path_problem(path) or not path.startswith(ELIGIBILITY_DIR):
        return None, f"the grant's {what} must be a file under {ELIGIBILITY_DIR}"
    try:
        return (Path(root) / path).read_bytes(), None
    except OSError:
        return None, f"{what} {path} is missing"


def _grant_problems(name: str, t: dict, root: Path | None) -> list[str]:
    """Why a task type above T2 may not load. The grant's report must be the one `autonomy.eligibility_report`
    computes from the grant's outcome log and evidence file; the loader recomputes it. The log and the evidence are
    trusted only as far as the guarded review of the change that committed them."""
    import hashlib

    from .autonomy import CRITERIA, eligibility_report, metrics
    tier, grant = t.get("tier"), t.get("autonomy_grant")
    untrusted = reads_untrusted(name)
    if tier not in ("T3", "T4") or (tier == "T3" and not untrusted):
        return []
    if not isinstance(grant, dict):
        return [f"{name}: {tier} needs an autonomy grant bound to an eligibility report"]
    typed = sorted(set(grant) & {"eligibility", "approvals", "verdict"})
    if typed:
        return [f"{name}: the grant types {', '.join(typed)}; a verdict comes from the report and approvals from "
                "the code host's review, never from the file"]
    if root is None:
        return [f"{name}: cannot read the eligibility report (no repository root)"]
    path, sha = grant.get("report"), grant.get("report_sha256")
    files = {}
    for key, what in (("report", "report"), ("outcomes", "outcome log"), ("evidence", "evidence file")):
        raw, problem = _read(root, grant.get(key), what)
        if problem:
            return [f"{name}: {problem}"]
        files[key] = raw
    if hashlib.sha256(files["report"]).hexdigest() != sha:
        return [f"{name}: eligibility report {path} does not match the grant's hash"]
    report = json.loads(files["report"].decode("utf-8"))
    try:
        log, evidence = json.loads(files["outcomes"].decode("utf-8")), json.loads(files["evidence"].decode("utf-8"))
        recomputed = eligibility_report(name, metrics(log, name), untrusted, evidence, str(grant.get("as_of")))
    except (ValueError, KeyError, TypeError) as exc:
        return [f"{name}: cannot recompute the report from the outcome log and evidence ({type(exc).__name__})"]
    if recomputed != report:
        return [f"{name}: report {path} is not the one recomputed from the outcome log and evidence"]
    problems = []
    if report.get("criteria_version") != CRITERIA or report.get("task_type") != name:
        problems.append(f"{name}: the report is not {CRITERIA} for this task type")
    passed = {c.get("cid"): c.get("passed") is True for c in report.get("criteria", [])}
    if untrusted and not passed.get("A4"):
        problems.append(f"{name}: reads untrusted input and A4 (coverage gate and live attack measurement) did not "
                        "pass: Chapter 12's T2 cap holds")
    if tier == "T4":
        failed = [c for c in ("A1", "A2", "A3", "A4", "A5", "A6", "A7") if not passed.get(c)]
        if failed:
            problems.append(f"{name}: T4 needs every criterion passed; failed or missing: {', '.join(failed)}")
    return problems


def validate(data: dict, root: Path | None = None) -> list[str]:
    """Problems with a policy document, in a stable order. An empty list means it may be loaded.

    `root` is the repository the policy belongs to, from which an eligibility report is read; without it no task
    type above T2 that needs a report can load.
    """
    problems: list[str] = []
    protected = list(data.get("protected_paths", []))
    teams = {k: list(v) for k, v in data.get("teams_declared", {}).items()}
    people = set(data.get("people", []))
    owner = data.get("bot_owner")
    if owner not in people:
        problems.append("bot_owner must be a person")
    for required in ("AGENTS.md", ".github/", "governance/", "maintenance/", "src/relay/maintenance/"):
        if required not in protected:
            problems.append(f"protected_paths must include {required}")
    for name, t in sorted(data.get("task_types", {}).items()):
        tier = t.get("tier")
        if tier not in TIERS:
            problems.append(f"{name}: unknown tier {tier!r}")
        if not t.get("approval_teams"):
            problems.append(f"{name}: names no approval team")
        for team in t.get("approval_teams", []):
            if team not in teams:
                problems.append(f"{name}: team {team} has no declared members")
        for w in t.get("write_paths", []):
            folded = w.rstrip("*").casefold()
            if path_problem(w.rstrip("/*")) or any(_under(folded, p.casefold()) for p in protected):
                problems.append(f"{name}: write path {w} lies inside a protected path or is not a plain path")
        if "reads_untrusted" in t and bool(t["reads_untrusted"]) != reads_untrusted(name):
            problems.append(f"{name}: reads_untrusted is derived from the task type's inputs and is "
                            f"{reads_untrusted(name)}, not {t['reads_untrusted']}")
        problems += _grant_problems(name, t, root)
        if t.get("self_modification"):
            problems.append(f"{name}: self-modifying task types are refused by this loader; one needs a new ADR, an "
                            "approved safety and security case and a reviewed loader change")
    return problems


def load(data: dict, root: Path | None = None) -> Policy:
    problems = validate(data, root)
    if problems:
        raise ValueError("; ".join(problems))
    types = {}
    for name, t in data["task_types"].items():
        types[name] = TaskType(
            name, t["tier"], tuple(t.get("write_paths", ())), tuple(t["approval_teams"]),
            reads_untrusted(name), bool(t.get("security_review", False)), t.get("guard_metric"),
            dict(t.get("budget", {})), bool(t.get("self_modification", False)), t.get("safety_case"),
            t.get("autonomy_grant"))
    return Policy(data["policy"], data["agent_id"], data["bot_owner"], tuple(data["protected_paths"]),
                  frozenset(data.get("sensitive_packages", [])),
                  {k: frozenset(v) for k, v in data["teams_declared"].items()}, types,
                  dict(data.get("safety_cases", {})))


def load_file(path: Path) -> Policy:
    path = Path(path)
    return load(json.loads(path.read_text(encoding="utf-8")), root=path.resolve().parent.parent)


class CodeOwners:
    """GitHub's CODEOWNERS rules, as far as Relay uses them: the last matching line wins.

    `/x/` matches a folder from the root, `/x` one path from the root, `*` everything, and a pattern without a
    leading slash matches at any depth. A path no line matches has no owner.
    """

    def __init__(self, text: str) -> None:
        self.rules: list[tuple[str, tuple[str, ...]]] = []
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            pattern, *owners = line.split()
            self.rules.append((pattern, tuple(owners)))

    @staticmethod
    def _match(pattern: str, path: str) -> bool:
        if pattern == "*":
            return True
        anchored = pattern.startswith("/")
        p = pattern.lstrip("/")
        if p.endswith("/"):
            return path.startswith(p) if anchored else (path.startswith(p) or f"/{p}" in f"/{path}")
        if anchored:
            return fnmatch.fnmatchcase(path, p) or path.startswith(p + "/")
        return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], p) or fnmatch.fnmatchcase(path, p)

    def owners(self, path: str) -> tuple[str, ...]:
        found: tuple[str, ...] = ()
        for pattern, owners in self.rules:
            if self._match(pattern, path):
                found = owners
        return found


def approver_problem(policy: Policy, owners: CodeOwners, person: str, task_type: str,
                     paths: list[str], packages: list[str]) -> str | None:
    """Why `person` may not approve a proposal of `task_type` touching `paths`, or None.

    The caller has already authenticated `person` (a fresh proof from the person issuer). Checked here:
    the bot's owner never approves its bot's work; the person is in an owning team of every path; the person is in
    one of the task type's approval teams; and a security-sensitive package or a task type with `security_review`
    needs a member of `@relay/security`.
    """
    t = policy.task_types.get(task_type)
    if t is None:
        return "unknown_task_type"
    if person == policy.bot_owner:
        return "bot_owner_may_not_approve"
    member = {team for team, people in policy.teams.items() if person in people}
    for path in paths:
        if not set(owners.owners(path)) & member:
            return f"not_a_code_owner:{path}"
    if not set(t.approval_teams) & member:
        return "not_in_an_approval_team"
    if (t.security_review or set(packages) & policy.sensitive_packages) and "@relay/security" not in member:
        return "security_review_required"
    return None

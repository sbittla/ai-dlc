"""The pipeline guard: a gate diff for workflow changes, and the review rules for any pipeline change
(TODO 2 in starter/). Policy: Relay's `governance/pipeline-guard.json` (relay-pipeline-guard-v1).

Gate diff, base workflow against head workflow, for the jobs that produce required checks:

    GD001  a required check's job is gone (removed or renamed)
    GD002  a required check's job gains or changes an `if:` (a skipped job reports success)
    GD003  `continue-on-error` other than literal `false` appears on a required job or one of its steps
    GD004  a step of a required job gains a way not to fail: a `||` fallback, `set +e`, or `exit 0`
    GD005  a step of a required job writes a report file itself (`> x.sarif`, `tee x.sarif`, `touch x.sarif`)
    GD006  the workflow stops running on every pull request (trigger removed, or paths/branches filters added)
    GD007  a required job loses a step (fewer steps, or a named step disappears)
    GD008  permissions broaden: a write scope or id-token appears at the top level or in a required job
    GD009  any other change to a required job's commands: a step's `run`, `uses` (other than a new commit SHA for
           the same action), `with`, `env` or `if` differs, or a step is added
    GD010  a file of gate configuration changes (the policy's `gate_config_paths`: scanner and gate policy, the
           mirror, labels, admission and rollout policy, the guard's own policy and the required-workflow list)

GD001-GD008 name common weakenings; they are not every weakening. GD009 and GD010 are the backstop: any change to
what a required job runs, or to what a gate reads as policy, is treated as a gate change.

Review rules, for a pull request that touches any pipeline path:

    PG001  the pull request also changes files outside the pipeline paths
    PG002  fewer than two approvals by people after the last push, or none from the owner team. An approval
           by the author, by an agent, or by the person who asked the agent for the change does not count
    PG003  a gate change (any GD finding) without an approval from the weakening team (counted as in PG002), or without a
           description line `Gate change: RLY-n: <reason of 20+ characters>` (INC-n also accepted)
    PG004  team membership could not be read: the guard cannot decide (exit 2); it never passes
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import yamlish
from .lint import triggers

FALLBACK = re.compile(r"\|\|(?!\s*$)|\bset\s+\+e\b|(^|[;&\n]\s*)exit\s+0\b")
WRITES_REPORT = re.compile(r"(>\s*|tee\s+(-a\s+)?|touch\s+)\S*\.(sarif|json)\b")
REASON = re.compile(r"^Gate change: (RLY|INC)-\d+: .{20,}$", re.MULTILINE)


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    message: str


def _job_for_check(jobs: dict, check: str) -> tuple[str, dict] | None:
    for key, job in jobs.items():
        if isinstance(job, dict) and (job.get("name") == check or (key == check and "name" not in job)):
            return key, job
    return None


def _write_scopes(perms) -> set[str]:
    if perms == "write-all":
        return {"*"}
    return {k for k, v in perms.items() if v == "write"} if isinstance(perms, dict) else set()


def _on_every_pr(doc: dict) -> bool:
    on = doc.get("on")
    if "pull_request" not in triggers(doc):
        return False
    if isinstance(on, dict) and isinstance(on.get("pull_request"), dict):
        return not {"paths", "paths-ignore", "branches", "branches-ignore"} & set(on["pull_request"])
    return True


def gate_diff(base: dict, head: dict, required: list[str], path: str = "workflow") -> list[Finding]:
    """GD findings for one workflow file, in rule order, then check order. Only required checks whose job
    exists in `base` are compared: a workflow that never produced a required check cannot weaken one."""
    out: dict[str, list[Finding]] = {f"GD{n:03d}": [] for n in range(1, 11)}
    bjobs, hjobs = base.get("jobs") or {}, head.get("jobs") or {}
    compared = []
    for check in required:
        b = _job_for_check(bjobs, check)
        if b is None:
            continue
        h = _job_for_check(hjobs, check)
        where = f"{path}:{check}"
        if h is None:
            out["GD001"].append(Finding("GD001", where, f"the job producing '{check}' is gone"))
            continue
        compared.append(check)
        before = sum(map(len, out.values()))
        bj, hj = b[1], h[1]
        if hj.get("if") is not None and hj.get("if") != bj.get("if"):
            out["GD002"].append(Finding("GD002", where, f"condition on a required job: if: {hj.get('if')}"))
        bsteps = [s for s in bj.get("steps") or [] if isinstance(s, dict)]
        hsteps = [s for s in hj.get("steps") or [] if isinstance(s, dict)]
        if hj.get("continue-on-error") not in (None, False) and hj.get("continue-on-error") != bj.get("continue-on-error"):
            out["GD003"].append(Finding("GD003", where, "continue-on-error on the job"))
        base_cont = {s.get("name") or s.get("uses") or s.get("run") for s in bsteps if s.get("continue-on-error")}
        for s in hsteps:
            if s.get("continue-on-error") not in (None, False) and (s.get("name") or s.get("uses") or s.get("run")) \
                    not in base_cont:
                out["GD003"].append(Finding("GD003", where, f"continue-on-error on step {s.get('name') or '?'}"))
        base_runs = [str(s.get("run", "")) for s in bsteps]
        for s in hsteps:
            run = s.get("run")
            if not isinstance(run, str):
                continue
            label = s.get("name") or run.split()[0]
            if FALLBACK.search(run) and not any(FALLBACK.search(r) for r in base_runs if r and r.split()[:2]
                                                == run.split()[:2]):
                out["GD004"].append(Finding("GD004", where, f"step '{label}' can no longer fail"))
            if WRITES_REPORT.search(run) and not any(WRITES_REPORT.search(r) for r in base_runs
                                                     if r and r.split()[:2] == run.split()[:2]):
                out["GD005"].append(Finding("GD005", where, f"step '{label}' writes a report itself"))
        names = {s.get("name") for s in hsteps if s.get("name")}
        lost = [s.get("name") for s in bsteps if s.get("name") and s.get("name") not in names]
        if len(hsteps) < len(bsteps) or lost:
            out["GD007"].append(Finding("GD007", where, "steps removed: " + (", ".join(lost) or
                                                                             f"{len(bsteps)} -> {len(hsteps)}")))
        added = _write_scopes(hj.get("permissions")) - _write_scopes(bj.get("permissions"))
        if added:
            out["GD008"].append(Finding("GD008", where, "write scopes added: " + ", ".join(sorted(added))))
        if sum(map(len, out.values())) == before and _commands(hsteps) != _commands(bsteps):
            changed = [s.get("name") or s.get("uses") or str(s.get("run", ""))[:40]
                       for s in hsteps if _command(s) not in [_command(b) for b in bsteps]]
            out["GD009"].append(Finding("GD009", where, "commands changed: " + ", ".join(changed)))
    if compared and _on_every_pr(base) and not _on_every_pr(head):
        out["GD006"].append(Finding("GD006", f"{path}:on", "no longer runs on every pull request"))
    top_added = _write_scopes(head.get("permissions")) - _write_scopes(base.get("permissions"))
    if compared and top_added:
        out["GD008"].append(Finding("GD008", f"{path}:permissions", "write scopes added at the top level: "
                                    + ", ".join(sorted(top_added))))
    return [f for rule in sorted(out) for f in out[rule]]


def _under(path: str, prefixes) -> bool:
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def is_pipeline_path(path: str, policy: dict) -> bool:
    return _under(path, policy["pipeline_paths"])


def _command(step: dict) -> tuple:
    """What a step runs, with an action's commit SHA dropped (a pin bump to the same action is not a change)."""
    uses = step.get("uses")
    if isinstance(uses, str) and "@" in uses:
        uses = uses.split("@", 1)[0]
    return (repr(step.get("run")), uses, repr(step.get("with")), repr(step.get("env")), repr(step.get("if")))


def _commands(steps: list[dict]) -> list[tuple]:
    return [_command(s) for s in steps]


def valid_approvers(pr: dict, agents: set[str]) -> list[str]:
    """People whose approval counts: after the last push, not the author, not an agent, not the agent's requester."""
    requester = (pr.get("agent") or {}).get("requester")
    out = []
    for a in pr.get("approvals", []):
        who = a["by"]
        if not a.get("after_last_push") or who == pr["author"] or who == requester:
            continue
        if who in agents or who.startswith("agent:") or who.endswith("[bot]"):
            continue
        if who not in out:
            out.append(who)
    return out


def guard(pr: dict, policy: dict, teams: dict | None, required: list[str]) -> list[Finding]:
    """GD findings for every changed workflow, then PG findings. `teams` maps team -> members and has the key
    "agents"; None means membership could not be read."""
    changed = pr["files"]
    pipeline = [f for f in changed if is_pipeline_path(f, policy)]
    if not pipeline:
        return []
    if teams is None:
        return [Finding("PG004", f"#{pr['number']}", "team membership could not be read; the guard cannot decide")]
    weak: list[Finding] = []
    for path, (base_text, head_text) in sorted((pr.get("workflows") or {}).items()):
        base = yamlish.loads(base_text) if base_text else {}
        head = yamlish.loads(head_text) if head_text else {}
        weak += gate_diff(base, head, required, path)
    weak += [Finding("GD010", f, "gate configuration changed") for f in changed
             if _under(f, policy.get("gate_config_paths", []))]
    out = list(weak)
    where = f"#{pr['number']}"
    others = [f for f in changed if f not in pipeline]
    if others:
        out.append(Finding("PG001", where, f"pipeline change mixed with {len(others)} other file(s): "
                           + ", ".join(others[:3]) + (" …" if len(others) > 3 else "")))
    approvers = valid_approvers(pr, set(teams.get("agents", [])))
    owners = set(teams.get(policy["owner_team"], []))
    if len(approvers) < 2 or not owners & set(approvers):
        out.append(Finding("PG002", where, f"{len(approvers)} counted approval(s), "
                           f"{len(owners & set(approvers))} from {policy['owner_team']}; need 2 and 1"))
    if weak:
        security = set(teams.get(policy["weakening_team"], []))
        if not security & set(approvers):
            out.append(Finding("PG003", where, f"gate change without an approval from {policy['weakening_team']}"))
        elif not REASON.search(pr.get("description", "")):
            out.append(Finding("PG003", where, "gate change without a 'Gate change: RLY-n: …' reason"))
    return out


def decision(findings: list[Finding]) -> tuple[str, int]:
    """('pass' | 'block' | 'cannot decide', exit code). GD findings alone never block: PG003 does."""
    if any(f.rule == "PG004" for f in findings):
        return "cannot decide", 2
    if any(f.rule.startswith("PG") for f in findings):
        return "block", 1
    return "pass", 0

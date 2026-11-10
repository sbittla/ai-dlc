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
    raise NotImplementedError("TODO 2: gate_diff")


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
    raise NotImplementedError("TODO 2: guard")


def decision(findings: list[Finding]) -> tuple[str, int]:
    """('pass' | 'block' | 'cannot decide', exit code). GD findings alone never block: PG003 does."""
    if any(f.rule == "PG004" for f in findings):
        return "cannot decide", 2
    if any(f.rule.startswith("PG") for f in findings):
        return "block", 1
    return "pass", 0

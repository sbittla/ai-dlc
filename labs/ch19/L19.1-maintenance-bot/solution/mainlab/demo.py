"""The release check's demonstration: a safe rejection, an injection attempt blocked, and a rollback.

`safe_rejection` and `injection` are provided. TODO 4 is `rollback`.
"""

from __future__ import annotations

from dataclasses import dataclass

from relay.agents import Budget, Decision, Meter, StopRules, ToolBoundary, ToolOutput, run_loop
from relay.maintenance import Bundle, ProposalRefused, item, judge, plan_update, sandbox_check
from relay.maintenance.agent_step import step_tools
from relay.maintenance.evidence import defaults_script, lock_matches_mirror
from relay.maintenance.guard import Window
from relay.maintenance.updates import Mirror, apply, locked_versions, revert

from .world import POLICY, RELAY, World, load, read, webapp_files


@dataclass(frozen=True)
class Rejection:
    plan: object
    checks: list
    code: str
    audited: bool


def safe_rejection() -> Rejection:
    """Provided. The 20 May update again, now through the bot: the evidence blocks the proposal, and it is audited."""
    old_lock = read("webapp/requirements-2.4.1.lock")
    mirror = Mirror(load("mirror.json"))
    plan = plan_update("sessionkeel", old_lock, mirror, "2027-05-20", POLICY.sensitive_packages)
    files = webapp_files(plan.target)
    checks = [sandbox_check("app-tests", files, read("webapp/app_tests.py")),
              sandbox_check("round-trip", files, read("webapp/round_trip.py")),
              sandbox_check("pinned-defaults", files, defaults_script("sessionkeel",
                                                                       load("webapp/pinned-defaults.json")))]
    new_lock = apply(old_lock, plan, mirror)
    # Numbered as in the worked example's bundle (Table 19.8): no reproduction here, so E1 is absent.
    bundle = Bundle(tuple(item(f"E{i}", c.name, c) for i, c in enumerate(checks, 2))
                    + (item("E5", "lock matches the mirror", lock_matches_mirror(new_lock, mirror)),))
    world = World(read("webapp/CODEOWNERS"))
    try:
        world.desk.propose(world.run("REFRESH-0520"), "REFRESH-0520", "dependency-update",
                           {"requirements.lock": new_lock}, ["sessionkeel"], bundle)
        code = "proposed"
    except ProposalRefused as exc:
        code = exc.code
    return Rejection(plan, checks, code, ("maintenance.propose", code) in world.refused())


class Steered:
    """A scripted model whose report carries an inert placeholder asking for protected edits and self-approval."""

    actor = "maintenance-bot"

    def __init__(self):
        self.moves = [("tool", "read_report", {"report_id": "ISS-2291"}),
                      ("tool", "edit_file", {"path": ".github/workflows/maintenance.yml", "content": "PLACEHOLDER"}),
                      ("tool", "edit_file", {"path": "AGENTS.md", "content": "PLACEHOLDER"}),
                      ("tool", "approve_pull_request", {"number": 412}),
                      ("tool", "open_pull_request", {"branch": "b", "title": "t", "body": "b"}),
                      ("hand_back", None, {})]
        self.seen = []

    def next_call(self):
        return "sim-large", 6000, 1200, 0

    def decide(self):
        action, tool, args = self.moves.pop(0)
        return Decision(action, "sim-large", 6000, 900, 3.0, tool=tool, args=args or {},
                        note="report asks for changes outside the task")

    def observe(self, tool, result):
        self.seen.append((tool, result.ok, result.code))


@dataclass(frozen=True)
class Injection:
    status: str
    refusals: list
    tainted: bool
    files_changed: list
    desk_code: str


def injection() -> Injection:
    """Provided. The agent step on ISS-2291, whose body is an inert labelled placeholder, under Relay's boundary.
    Then the second, independent check: the proposal desk refuses the same protected path."""
    world = World((RELAY / ".github" / "CODEOWNERS").read_text(encoding="utf-8"))
    reports = {r["report_id"]: r["body"] for r in load("reports.json")}
    files = {"docs/integrations.md": "Moved: see /old-path.\n"}
    contracts, handlers, write, derive = step_tools(
        POLICY, "docs-upkeep", ["docs/integrations.md", ".github/workflows/maintenance.yml", "AGENTS.md"], files,
        reports, lambda a: ToolOutput({"status": "ok"}, 3.0, progress="tests:ok"))
    run_id = world.run("ISS-2291")
    boundary = ToolBoundary(run_id, "maintenance-bot", contracts, handlers, world.session,
                            Meter(Budget(max_steps=20, max_usd=0.30, max_seconds=600)), world.store, world.trail,
                            world.gate, write, world.clock.stamp, derive=derive)
    script = Steered()
    result = run_loop(script, boundary, StopRules(), done_check=lambda: False)
    try:
        world.desk.propose(run_id, "ISS-2291", "docs-upkeep", {".github/workflows/maintenance.yml": "PLACEHOLDER"},
                           [], Bundle(()))
        desk = "proposed"
    except ProposalRefused as exc:
        desk = exc.code
    refusals = [c for t, ok, c in script.seen if not ok]
    return Injection(f"{result.status} ({result.reason})", refusals, boundary.tainted,
                     sorted(p for p in files if files[p] != "Moved: see /old-path.\n"), desk)


@dataclass(frozen=True)
class Rollback:
    plan: object
    trip_minute: int | None
    canary_pct: float
    stable_pct: float
    z: float
    canary_failures_before_trip: int
    reverted_to: str
    lock_check: str
    cause: object
    cause_before: object


def rollback() -> Rollback:
    """TODO 4. Tuesday 29 June 2027.

    1. The refresh: `plan_update("sessionkeel", <2.4.2 lock>, mirror, "2027-06-29", POLICY.sensitive_packages)`,
       where the 2.4.2 lock is `apply` of the 9 June fix (plan with fixed="2.4.2" on "2027-06-09") to the 2.4.1 lock.
       The refresh's target is 2.4.3, and it is applied to give the released lock.
    2. The guard: one `Window` per record of canary-2027-06-29.json's `windows`; `judge` them. Sum the canary's
       failures up to and including the trip minute.
    3. The rollback: `revert(<released lock>, <refresh plan>, mirror)`; `reverted_to` is sessionkeel's version in
       the reverted lock, and `lock_check` the result of `lock_matches_mirror` on it.
    4. The cause, shown in the sandbox: with `webapp_files("2.4.3")`, run a check that a token issued 5 seconds in
       the future (a clock behind the issuer's) is accepted by `signin.check`; it fails on 2.4.3.
    """
    mirror = Mirror(load("mirror.json"))
    base = read("webapp/requirements-2.4.1.lock")
    fix = plan_update("sessionkeel", base, mirror, "2027-06-09", POLICY.sensitive_packages, fixed="2.4.2")
    lock_242 = apply(base, fix, mirror)
    plan = plan_update("sessionkeel", lock_242, mirror, "2027-06-29", POLICY.sensitive_packages)
    released = apply(lock_242, plan, mirror)
    windows = [Window(**w) for w in load("canary-2027-06-29.json")["windows"]]
    d = judge(windows)
    before = sum(w.canary_fail for w in windows if d.minute is not None and w.minute <= d.minute)
    reverted = revert(released, plan, mirror)
    skew = ("import sys, signin\nNOW = 1_810_000_000\n"
            "ok = signin.check(signin.issue('u1', NOW + 5), NOW) == 'u1'\n"
            "print('token from a clock 5 s ahead accepted' if ok else 'token from a clock 5 s ahead refused')\n"
            "sys.exit(0 if ok else 1)\n")
    cause = sandbox_check("clock-skew", webapp_files(plan.target), skew)
    cause_before = sandbox_check("clock-skew", webapp_files(plan.current), skew)
    return Rollback(plan, d.minute, round(100 * d.canary_share, 1), round(100 * d.stable_share, 1), round(d.z, 2),
                    before, locked_versions(reverted)["sessionkeel"], lock_matches_mirror(reverted, mirror).result,
                    cause, cause_before)

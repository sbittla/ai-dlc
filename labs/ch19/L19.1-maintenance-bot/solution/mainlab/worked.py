"""The worked example: the bot reproduces LAB-ADV-2027-0113, proposes a fix with evidence, and waits.

TODO 3 `fix_vulnerability`: the whole workflow on Wednesday 9 June 2027, with the approvals that are refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from relay.agents import ApprovalRefused
from relay.maintenance import Bundle, Check, Report, item, plan_update, reproduce, sandbox_check, triage
from relay.maintenance.evidence import defaults_script, lock_matches_mirror
from relay.maintenance.updates import Mirror, apply, locked_versions

from .world import POLICY, World, load, read, webapp_files

SCAN_RECORD = Check("security-gates", "pass", "relay-security-gates-v1: 0 findings on this diff (record supplied)")


@dataclass
class Worked:
    triage: object = None
    reproduction: object = None
    plan: object = None
    checks: list = field(default_factory=list)
    bundle: Bundle | None = None
    proposal: object = None
    refusals: list = field(default_factory=list)
    decided: object = None
    pr: dict | None = None
    world: World | None = None


def fix_vulnerability() -> Worked:
    """TODO 3. In order, filling a `Worked`:

    1. Triage the report "ADV-0113" from reports.json (a `Report(report_id, source, form, body)`) against the
       versions in `webapp/requirements-2.4.1.lock`.
    2. Plan with `plan_update(..., "2027-06-09", POLICY.sensitive_packages, fixed=<the triage's fixed>,
       advisory=<its advisory>)` and apply it to the lock (`apply`).
    3. Reproduce with `reproduce(webapp_files(<locked>), webapp_files(<target>), <webapp/repro_adv_0113.py>)`.
    4. Checks on the target, in this order, each a `Check`: the app tests, the round trip, the pinned defaults
       (all three with `sandbox_check`), and `lock_matches_mirror(new lock, mirror)`.
    5. The bundle, items E1 to E6: E1 reproduction (its `after` check), E2-E4 the three sandbox checks, E5 the
       lock check, all `verified`; E6 `SCAN_RECORD`, `modelled`, source "security-gates record".
    6. A `World(read("webapp/CODEOWNERS"))`; propose task "ADV-0113" of the triage's task type, path
       changes {"requirements.lock": <new lock>}, package "sessionkeel" (the desk derives the paths, the diff's
       hash and every package in the changed lock itself).
    7. Try to decide as the bot (`world.proof()`), then priya.n, then sam.o (each refused: record the codes in
       `refusals`), then aisha.r approves. Then open the pull request with `world.open_pr`.
    """
    w = Worked()
    report = next(r for r in load("reports.json") if r["report_id"] == "ADV-0113")
    old_lock = read("webapp/requirements-2.4.1.lock")
    mirror = Mirror(load("mirror.json"))
    w.triage = triage(Report(report["report_id"], report["source"], report["form"], report["body"]),
                      locked_versions(old_lock))
    w.plan = plan_update("sessionkeel", old_lock, mirror, "2027-06-09", POLICY.sensitive_packages,
                         fixed=w.triage.fields["fixed"], advisory=w.triage.fields["advisory"])
    new_lock = apply(old_lock, w.plan, mirror)
    after = webapp_files(w.plan.target)
    w.reproduction = reproduce(webapp_files(w.plan.current), after, read("webapp/repro_adv_0113.py"))
    w.checks = [sandbox_check("app-tests", after, read("webapp/app_tests.py")),
                sandbox_check("round-trip", after, read("webapp/round_trip.py")),
                sandbox_check("pinned-defaults", after,
                              defaults_script("sessionkeel", load("webapp/pinned-defaults.json"))),
                lock_matches_mirror(new_lock, mirror)]
    claims = ["the advisory's test fails on 2.4.1 and passes on the fix", "the app's tests pass",
              "a token sign-in issues is accepted", "security-relevant defaults are unchanged",
              "every locked file's hash is the mirror's"]
    w.bundle = Bundle(tuple(item(f"E{i}", c, chk) for i, (c, chk) in
                            enumerate(zip(claims, [w.reproduction.after] + w.checks), 1))
                      + (item("E6", "no scanner finding on the diff", SCAN_RECORD, status="modelled",
                              source="security-gates record"),))
    world = World(read("webapp/CODEOWNERS"))
    w.world = world
    w.proposal = world.desk.propose(world.run("ADV-0113"), "ADV-0113", w.triage.task_type,
                                    {"requirements.lock": new_lock}, ["sessionkeel"], w.bundle)
    for proof in (world.proof(), world.person("priya.n"), world.person("sam.o")):
        try:
            world.desk.decide(w.proposal.proposal_id, proof, True, "approve")
        except ApprovalRefused as exc:
            w.refusals.append(exc.code)
    world.clock.t += 3 * 3600 + 12 * 60
    w.decided = world.desk.decide(w.proposal.proposal_id, world.person("aisha.r"), True,
                                  "LAB-ADV-2027-0113: reproduced and fixed; defaults unchanged")
    w.pr = world.desk.open_pull_request(w.proposal.proposal_id, {"requirements.lock": new_lock}, w.bundle.sha256(),
                                        world.open_pr)
    return w

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
    raise NotImplementedError("TODO 3: fix_vulnerability")

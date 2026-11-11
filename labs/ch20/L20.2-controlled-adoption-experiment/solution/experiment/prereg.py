"""Check a pre-registration before the pilot starts (Chapter 20, Section 20.5). Rules REG001-REG011.

A pre-registration is written, dated and frozen before any outcome data exists. It names one primary outcome,
the comparison, the randomization and its unit, the contamination risks, the power of the registered test for a
stated minimum detectable effect, the analysis and its stopping rule, the guardrails and who analyses the data.
The check cannot tell whether the plan is wise; it tells whether the plan exists in a form nobody can quietly
change later.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

ALLOWED_PRIMARY = {
    # DORA delivery measures as Chapter 1 defines them (Table 1.8)
    "change_lead_time", "deployment_frequency", "failed_deployment_recovery_time", "change_fail_rate",
    "rework_rate",
    # SPACE-aligned measures from an anonymous survey
    "satisfaction", "flow", "review_load_manageable", "psychological_safety",
}
ALLOWED_SECONDARY = ALLOWED_PRIMARY | {"author_hours", "review_hours", "review_wait", "unassisted_debugging_pass"}
BANNED = re.compile(r"lines?_of_code|loc\b|prompts?|suggestions?|acceptance_rate|pull_requests?|\bprs?\b|pr_count|"
                    r"commits?|tokens?|story_points", re.IGNORECASE)
CLUSTER_FOR_DESIGN = {"D1": "team", "D2": "engineer", "D3": "engineer", "D4": "engineer"}
MIN_POWER = 0.80
POWER_TOLERANCE = 0.03
UNPLANNED_LOOKS = re.compile(r"peek|dashboard|stop when|weekly|daily|monthly", re.IGNORECASE)
SPENDING_FUNCTION = re.compile(r"o'?brien-fleming|pocock|lan-demets", re.IGNORECASE)
RANDOM_METHODS = re.compile(r"permuted blocks?|block randomi[sz]ation|stratified randomi[sz]ation|"
                            r"simple randomi[sz]ation|seeded (shuffle|random)|random number|drawn by lot|coin",
                            re.IGNORECASE)
CHOICE = re.compile(r"volunteer|chose|choose|pick|opt[- ]?in|self[- ]?select|nominat", re.IGNORECASE)
PLACEHOLDERS = {"", "none", "tbd", "tbc", "todo", "n/a", "na", "-", "?"}


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str


def _missing(x) -> bool:
    """Blank, or a placeholder such as "TBD" or "none"."""
    return x is None or (isinstance(x, str) and x.strip().lower() in PLACEHOLDERS)


def _person(x) -> str:
    return (x or "").strip().lower()


def _day(x) -> date | None:
    try:
        return date.fromisoformat(x)
    except (TypeError, ValueError):
        return None


def registered_test(reg: dict) -> str:
    """The test the registration names: "sign" for a sign test, otherwise "t" (provided)."""
    return "sign" if "sign" in (reg.get("analysis", {}).get("test") or "").lower() else "t"


def check_prereg(reg: dict, computed_power: float | None = None,
                 assignment_sha256: str | None = None) -> list[Finding]:
    """Return the findings for one pre-registration, sorted by rule then message.

    computed_power: this lab's simulate_power for the registration's design, minimum detectable effect and
    registered test (registered_test). assignment_sha256: the SHA-256 of the assignment list actually used.
    People are compared after strip() and lower(). A value is missing when _missing() says so.

    REG001 registered_on or start is not an ISO date, or registered_on is not before start
    REG002 not exactly one primary outcome, or the primary is not in ALLOWED_PRIMARY
    REG003 for the primary and each secondary outcome: BANNED matches it ("output metric ... is not an outcome"),
           or else a secondary outside ALLOWED_SECONDARY ("... is not an allowed outcome"); one finding each
    REG004 randomization incomplete, ONE finding listing every problem: missing method, a method that names no
           random procedure (RANDOM_METHODS), people choose their arm (CHOICE matches), the seed is not an int, no 64-hex assignment hash, the hash
           differs from the list used, or the sponsor assigns
    REG005 comparison group missing
    REG006 no contamination risk whose risk and mitigation are both present
    REG007 the power's design differs from the registration's; or stated power below MIN_POWER; or more than
           POWER_TOLERANCE from computed_power (which must be for the registered test)
    REG008 analysis incomplete, ONE finding listing every problem: missing interval or test, cluster unit not
           CLUSTER_FOR_DESIGN[design], or interim looks that neither name a spending function (SPENDING_FUNCTION)
           nor start with "none" free of UNPLANNED_LOOKS
    REG009 a guardrail whose threshold or window is missing (one finding each); no guardrail on change_fail_rate;
           none on review_hours or review_wait
    REG010 the sponsor is the analysis owner or the data steward
    """
    out: list[Finding] = []
    reg_day, start_day = _day(reg.get("registered_on")), _day(reg.get("start"))
    if reg_day is None or start_day is None or reg_day >= start_day:
        out.append(Finding("REG001", f"registered {reg.get('registered_on')} is not a date before the start "
                                     f"{reg.get('start')}"))
    primary = reg.get("primary_outcome")
    pm = primary.get("metric") if isinstance(primary, dict) else None
    if pm not in ALLOWED_PRIMARY:
        out.append(Finding("REG002", f"primary outcome {pm!r} is not a delivery or SPACE outcome"))
    if isinstance(pm, str) and BANNED.search(pm):
        out.append(Finding("REG003", f"output metric {pm} is not an outcome"))
    for sec in reg.get("secondary_outcomes", []):
        m = sec.get("metric", "")
        if BANNED.search(m):
            out.append(Finding("REG003", f"output metric {m} is not an outcome"))
        elif m not in ALLOWED_SECONDARY:
            out.append(Finding("REG003", f"{m} is not an allowed outcome"))
    rnd = reg.get("randomization", {})
    method = rnd.get("method") or ""
    sha = rnd.get("assignment_list_sha256") or ""
    problems = []
    if _missing(method):
        problems.append("no method")
    elif not RANDOM_METHODS.search(method):
        problems.append("no random procedure named")
    if CHOICE.search(method):
        problems.append("people choose their arm")
    if not isinstance(rnd.get("seed"), int) or isinstance(rnd.get("seed"), bool):
        problems.append("no seed")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        problems.append("no assignment-list hash")
    elif assignment_sha256 is not None and sha != assignment_sha256:
        problems.append("assignment list differs from the registered one")
    sponsor = _person(reg.get("sponsor"))
    if _person(rnd.get("who_assigns")) == sponsor:
        problems.append("the sponsor assigns")
    if problems:
        out.append(Finding("REG004", "randomization: " + ", ".join(problems)))
    if _missing(reg.get("comparison_group")):
        out.append(Finding("REG005", "no comparison group"))
    if not any(not _missing(c.get("risk")) and not _missing(c.get("mitigation")) for c in reg.get("contamination", [])):
        out.append(Finding("REG006", "no contamination risk with a mitigation"))
    pw = reg.get("power", {})
    stated = pw.get("power", 0.0)
    if pw.get("design") != reg.get("design"):
        out.append(Finding("REG007", f"power computed for {pw.get('design')}, design is {reg.get('design')}"))
    elif stated < MIN_POWER:
        out.append(Finding("REG007", f"stated power {stated:.2f} below {MIN_POWER:.2f}"))
    elif computed_power is not None and abs(stated - computed_power) > POWER_TOLERANCE:
        out.append(Finding("REG007", f"stated power {stated:.2f}, recomputed {computed_power:.2f}"))
    an = reg.get("analysis", {})
    problems = []
    if _missing(an.get("interval")):
        problems.append("no interval")
    if _missing(an.get("test")):
        problems.append("no test")
    if an.get("cluster_unit") != CLUSTER_FOR_DESIGN.get(reg.get("design")):
        problems.append(f"cluster unit {an.get('cluster_unit')!r}, design needs "
                        f"{CLUSTER_FOR_DESIGN.get(reg.get('design'))!r}")
    looks = (an.get("interim_looks") or "").strip()
    if not (SPENDING_FUNCTION.search(looks) or (looks.lower().startswith("none") and not UNPLANNED_LOOKS.search(looks))):
        problems.append("interim looks without a named alpha-spending function")
    if problems:
        out.append(Finding("REG008", "analysis: " + ", ".join(problems)))
    guards = reg.get("guardrails", [])
    for g in guards:
        if _missing(g.get("threshold")) or _missing(g.get("window")):
            out.append(Finding("REG009", f"guardrail {g.get('metric')} has no threshold or window"))
    names = {g.get("metric") for g in guards}
    if "change_fail_rate" not in names:
        out.append(Finding("REG009", "no guardrail on change_fail_rate"))
    if not names & {"review_hours", "review_wait"}:
        out.append(Finding("REG009", "no guardrail on review load"))
    if sponsor in (_person(reg.get("analysis_owner")), _person(reg.get("data_steward"))):
        out.append(Finding("REG010", "the sponsor analyses or holds the data"))
    return sorted(out, key=lambda f: (f.rule, f.message))


def check_frozen(reg_bytes: bytes, frozen: dict | None, reg_id: str, start_date: str) -> list[Finding]:
    """REG011 (provided): the registration's bytes hash to the record the data steward froze before the start
    date, and the record's frozen_on date is before start_date.

    A registration changed after it was frozen, such as a new primary outcome, fails here even if it passes
    REG001-REG010.
    """
    if not frozen or frozen.get("id") != reg_id:
        return [Finding("REG011", "no frozen record for this registration")]
    frozen_on, start = _day(frozen.get("frozen_on")), _day(start_date)
    if frozen_on is None or start is None or frozen_on >= start:
        return [Finding("REG011", "frozen on or after the start, or without a date")]
    if hashlib.sha256(reg_bytes).hexdigest() != frozen.get("sha256"):
        return [Finding("REG011", "registration changed after it was frozen")]
    return []

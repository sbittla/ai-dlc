"""An ROI model that keeps measured values apart from projections (Chapter 20, Section 20.5).

Every number the model uses is an input with a status (measured or projected), a source and a range. Measured
inputs come from the pilot, the baseline, a contract or finance, with a reference to what printed them.
Vendor claims are refused: they are not evidence about this company's work. Output metrics such as lines of
code or prompt counts are refused as inputs of any kind. The model refuses to run on inputs with findings.

Benefits are capacity: engineer hours released per agent change, net of the review hours agents add, valued at
a loaded hourly cost and discounted by a realization share (not every saved calendar hour becomes planned work).
Costs are model spend, seats, platform and governance effort, training and the juniors' unassisted practice.
"""

from __future__ import annotations

import re

from . import Finding

MEASURED_KINDS = {"pilot", "baseline", "contract", "finance"}
KINDS = MEASURED_KINDS | {"published-study", "estimate", "vendor-claim"}
KNOWN_REFS = ("Lab 20.2: python -m experiment.report", "Lab 20.2: data/", "Lab 1.1: data/", "signed order form")
BANNED = re.compile(r"lines?[_ ]of[_ ]code|\bloc\b|prompts?|suggestions?|pull[_ ]requests?|\bprs?\b|commits?",
                    re.IGNORECASE)
REQUIRED = ("author_hours_saved", "review_hours_added", "change_fail_rate_delta", "model_usd_per_agent_change",
            "changes_per_engineer_month", "seat_usd_per_engineer_month", "engineers", "juniors",
            "engineer_months_adopted", "agent_share", "realization", "hours_per_failed_change",
            "loaded_cost_per_engineer_month", "hours_per_engineer_month", "platform_fte", "governance_fte",
            "training_hours_per_engineer", "junior_practice_hours_per_month")


def check_inputs(inputs: list[dict]) -> list[Finding]:
    """Return findings ROI001-ROI008 for a list of inputs, sorted by rule then subject (the input id).

    ROI001 status is not "measured" or "projected"
    ROI002 status "measured" with a source kind outside MEASURED_KINDS, or a source ref that does not start with
           one of KNOWN_REFS (the commands and files this lab's tests can check)
    ROI003 source kind "vendor-claim", or "vendor" anywhere in the source ref (any case), whatever the status: a
           vendor's number is not evidence
    ROI004 not low <= value <= high; or status "projected" with low == high (a projection needs a range); or a
           measured input from the pilot with low == high (a pilot measurement has an interval)
    ROI005 BANNED matches the id or the label: an output metric
    ROI006 a REQUIRED input is missing (subject: the missing id)
    ROI007 an input id the model does not use (not in REQUIRED)
    ROI008 a source kind outside KINDS
    """
    out: list[Finding] = []
    ids = {i["id"] for i in inputs}
    for i in inputs:
        iid, status, src = i["id"], i.get("status", ""), i.get("source", {})
        kind, ref = src.get("kind"), (src.get("ref") or "").strip()
        if status not in ("measured", "projected"):
            out.append(Finding("ROI001", iid, f"status {status!r} is neither measured nor projected"))
        if status == "measured" and (kind not in MEASURED_KINDS or not ref.startswith(KNOWN_REFS)):
            out.append(Finding("ROI002", iid, f"marked measured but sourced from {kind!r} ({ref or 'no reference'})"))
        if kind == "vendor-claim" or "vendor" in ref.lower():
            out.append(Finding("ROI003", iid, "a vendor's claim is not evidence about this company's work"))
        if not (i["low"] <= i["value"] <= i["high"]) or (status == "projected" and i["low"] == i["high"]) or                 (status == "measured" and kind == "pilot" and i["low"] == i["high"]):
            out.append(Finding("ROI004", iid, "value outside its range, or no range where one is needed"))
        if BANNED.search(iid) or BANNED.search(i.get("label", "")):
            out.append(Finding("ROI005", iid, "an output metric, not an outcome"))
        if iid not in REQUIRED:
            out.append(Finding("ROI007", iid, "not used by the model"))
        if kind not in KINDS:
            out.append(Finding("ROI008", iid, f"unknown source kind {kind!r}"))
    for r in REQUIRED:
        if r not in ids:
            out.append(Finding("ROI006", r, "required input missing"))
    return sorted(out, key=lambda f: (f.rule, f.subject))


def evaluate(v: dict[str, float], months: int = 12, include_training: bool = True) -> dict[str, float]:
    """The model (provided). `v` maps input ids to values. Returns hours and dollars, benefit, cost and net."""
    per_hour = v["loaded_cost_per_engineer_month"] / v["hours_per_engineer_month"]
    agent_changes = v["engineer_months_adopted"] * v["changes_per_engineer_month"] * v["agent_share"]
    gross_hours = agent_changes * (v["author_hours_saved"] - v["review_hours_added"])
    failure_hours = agent_changes * v["change_fail_rate_delta"] / 100 * v["hours_per_failed_change"]
    benefit = (gross_hours * v["realization"] - failure_hours) * per_hour
    costs = {
        "model": agent_changes * v["model_usd_per_agent_change"],
        "seats": v["engineer_months_adopted"] * v["seat_usd_per_engineer_month"],
        "platform_and_governance": (v["platform_fte"] + v["governance_fte"]) * months
        * v["loaded_cost_per_engineer_month"],
        "training": (v["training_hours_per_engineer"] * v["engineers"] * per_hour) if include_training else 0.0,
        "junior_practice": v["juniors"] * v["junior_practice_hours_per_month"] * months * per_hour,
    }
    cost = sum(costs.values())
    return {"per_hour": per_hour, "agent_changes": agent_changes, "gross_hours": gross_hours,
            "failure_hours": failure_hours, "benefit": benefit, "cost": cost, "net": benefit - cost,
            **{f"cost_{k}": c for k, c in costs.items()}}


def values(inputs: list[dict], which: str = "value") -> dict[str, float]:
    return {i["id"]: i[which] for i in inputs}


def tornado(inputs: list[dict], **kw) -> list[tuple[str, float, float, float]]:
    """One-at-a-time sensitivity of the net result.

    For every input with low != high: evaluate the net with that input at its low and at its high, every other
    input at its value (pass **kw through to evaluate). Return (id, net_at_low, net_at_high, swing) tuples, where
    swing = abs(net_at_high - net_at_low), sorted by swing descending, then id.
    """
    base = values(inputs)
    rows = []
    for i in inputs:
        if i["low"] == i["high"]:
            continue
        lo = evaluate(dict(base, **{i["id"]: i["low"]}), **kw)["net"]
        hi = evaluate(dict(base, **{i["id"]: i["high"]}), **kw)["net"]
        rows.append((i["id"], lo, hi, abs(hi - lo)))
    return sorted(rows, key=lambda r: (-r[3], r[0]))


def break_even(inputs: list[dict], input_id: str, **kw) -> float:
    """The value of `input_id` at which the net is zero, others at their values (provided; the model is linear in
    every input used here except hours_per_engineer_month, so two evaluations suffice)."""
    base = values(inputs)
    a, b = 0.0, 1.0
    na = evaluate(dict(base, **{input_id: a}), **kw)["net"]
    nb = evaluate(dict(base, **{input_id: b}), **kw)["net"]
    return a - na * (b - a) / (nb - na)

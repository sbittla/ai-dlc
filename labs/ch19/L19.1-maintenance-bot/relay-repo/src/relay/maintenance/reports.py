"""Turning reports into maintenance tasks without letting their text decide anything (added in 4.31.0; ADR-053).

Reports come from outside: issues anyone can open, an advisory feed, support cases synced from customers. Their
free text is untrusted input (Chapter 2) and may carry instructions written for an agent (Chapter 12). So
triage here reads only **structured fields** that a form or a feed fills in, each checked against an allowlist
or a strict pattern, and never the body. The body travels with the task as data, marked untrusted; whatever
later reads it does so behind Chapter 10's boundary, and the run that reads it is tainted (ADR-034).

Every report is untrusted unless its source is the scheduler, which Relay itself runs; a missing or unknown
`source` is untrusted. A report that matches no rule goes to a person (`needs_person`), with the reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .semver import parse

SOURCES = frozenset({"advisory-feed", "issue-form", "support-sync", "schedule"})
TRUSTED_SOURCES = frozenset({"schedule"})
_PACKAGE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_ADVISORY = re.compile(r"^(?:LAB-ADV|GHSA|CVE|PYSEC)-[0-9A-Za-z-]{4,40}$")
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
DOC_COMPONENTS = frozenset({"docs", "api-docs", "runbooks"})
SCHEDULED_JOBS = {"dependency-refresh": "dependency-update", "dst-table": "table-extension"}


@dataclass(frozen=True)
class Report:
    report_id: str
    source: str
    form: dict = field(default_factory=dict)  # structured fields from a form or a feed
    body: str = ""                            # free text: data, never instructions

    @property
    def trusted(self) -> bool:
        return self.source in TRUSTED_SOURCES


@dataclass(frozen=True)
class Triage:
    report_id: str
    task_type: str | None      # None: a person decides
    reason: str
    fields: dict
    untrusted: bool


def triage(report: Report, locked: dict[str, str]) -> Triage:
    """The task a report becomes, from its structured fields only. `locked` maps package names to versions.

    - advisory-feed: `package`, `fixed` and `advisory` must be well formed; a package not in the lock is
      `not_ours`; otherwise `vulnerability-fix`, if the locked version is below `fixed`.
    - issue-form: `component` in DOC_COMPONENTS and `kind` "broken-link" gives `docs-upkeep`; `kind` "bug" with
      a `component` gives `bug-reproduction`. Nothing else.
    - schedule: `job` from SCHEDULED_JOBS.
    - support-sync and anything else: a person.
    """
    untrusted = not report.trusted
    form = report.form if isinstance(report.form, dict) else {}
    rid = report.report_id if isinstance(report.report_id, str) and _ID.match(report.report_id) else "?"

    def person(reason: str) -> Triage:
        return Triage(rid, None, reason, {}, untrusted)

    if rid == "?" or report.source not in SOURCES:
        return person("unknown_source_or_id")
    if report.source == "advisory-feed":
        pkg, fixed, adv = form.get("package"), form.get("fixed"), form.get("advisory")
        if not (isinstance(pkg, str) and _PACKAGE.match(pkg) and isinstance(adv, str) and _ADVISORY.match(adv)):
            return person("malformed_advisory")
        try:
            fixed_v = parse(fixed)
        except ValueError:
            return person("malformed_advisory")
        if pkg not in locked:
            return person("not_ours")
        if parse(locked[pkg]) >= fixed_v:
            return Triage(rid, None, "already_fixed", {"package": pkg}, untrusted)
        return Triage(rid, "vulnerability-fix", "advisory", {"package": pkg, "fixed": str(fixed_v),
                                                              "advisory": adv, "locked": locked[pkg]}, untrusted)
    if report.source == "issue-form":
        component, kind = form.get("component"), form.get("kind")
        if kind == "broken-link" and component in DOC_COMPONENTS:
            return Triage(rid, "docs-upkeep", "form", {"component": component}, untrusted)
        if kind == "bug" and isinstance(component, str) and _ID.match(component):
            return Triage(rid, "bug-reproduction", "form", {"component": component}, untrusted)
        return person("form_matches_no_task_type")
    if report.source == "schedule":
        job = form.get("job")
        if job in SCHEDULED_JOBS:
            return Triage(rid, SCHEDULED_JOBS[job], "schedule", {"job": job}, untrusted)
        return person("unknown_scheduled_job")
    return person("source_needs_a_person")

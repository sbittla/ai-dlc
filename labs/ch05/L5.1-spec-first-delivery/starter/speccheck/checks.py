"""The spec checker's checks.

Five functions are the lab's TODOs in starter/: check_sections, check_tests,
check_task_links, check_tiers and check_classification. Each docstring is the
specification; tests/test_checks.py checks each on inputs you can verify by hand.
Every other check is provided.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .core import (CLASSIFICATIONS, MAX_TASK_CHECKS, MAX_TASK_FILES, REQUIRED_HEADER, REQUIRED_SECTIONS, RISKS,
                   TIERS, UNTRUSTED_CAP, Finding, finding)
from .repo import criterion_of
from .spec import Contract, Prd, Spec, Task, TaskList, load_contract, load_spec, load_tasks

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


# ------------------------------------------------------------------ TODO 1

def check_sections(spec: Spec) -> list[Finding]:
    """SP010 for each required section (core.REQUIRED_SECTIONS) missing from `spec.sections`,
    and SP011 for each one that is present but empty (only whitespace) or contains the text
    "TO COMPLETE". Report in the order of REQUIRED_SECTIONS; the item is the section name.
    """
    raise NotImplementedError('check_sections')


# ------------------------------------------------------------------ TODO 2

def check_tests(spec: Spec, tests: tuple[str, ...]) -> list[Finding]:
    """Link every criterion to a test with its ID, using repo.criterion_of(test_name).

    - SP030 for each criterion in the spec (in spec order) with no test whose ID equals
      the criterion's ID. Item: the criterion ID.
    - SP031 for each distinct criterion ID carried by a test name that is not a criterion
      in this spec, sorted by ID. Item: the ID; the message names the test(s).
    Tests whose names carry no criterion ID are ignored.
    """
    raise NotImplementedError('check_tests')


# ------------------------------------------------------------------ TODO 3

def check_task_links(spec: Spec, tasks: TaskList) -> list[Finding]:
    """Link tasks to the criteria and security constraints they check (spec.ids()).

    - SP040 for each task (in task order) whose Checks is empty. Item: the task ID.
    - SP041 for each ID a task checks that spec.ids() does not contain, in task order and
      then in the order the task lists them. Item: the task ID; the message names the ID.
    - SP042 for each criterion (spec order) and then each security constraint (spec order)
      that no task checks. Item: the criterion or constraint ID.
    """
    raise NotImplementedError('check_task_links')


# ------------------------------------------------------------------ TODO 4

def check_tiers(tasks: TaskList) -> list[Finding]:
    """Chapter 1's autonomy tiers, one per task, in task order. For each task, at most one finding:

    - SP050 if its tier is not one of core.TIERS (T0-T4), including an empty tier.
    - otherwise SP051 if it reads untrusted input (untrusted == "yes") at a tier above
      core.UNTRUSTED_CAP (T2). The cap applies whatever the other answers are.
    - otherwise SP052 if it is sensitive (sensitive == "yes") at T4. A task list marks
      irreversible work as sensitive too: Chapter 1 never allows T4 for either.
    Item: the task ID.
    """
    raise NotImplementedError('check_tiers')


# ------------------------------------------------------------------ TODO 5

def check_classification(spec: Spec, contract: Contract | None) -> list[Finding]:
    """Every field the contract defines has a data classification.

    - If spec.data_rules is empty: one SP060 with item "Data rules", and nothing else.
    - SP061 for each field in spec.data_rules whose classification is not one of
      core.CLASSIFICATIONS, in table order. Item: the field.
    - If `contract` is not None: SP060 for each field in contract.fields (in contract order)
      that spec.data_rules does not list. Item: the field, such as "Rule.rule_id".
    """
    raise NotImplementedError('check_classification')


# ------------------------------------------------------------------ provided

def check_header(spec: Spec, prd: Prd) -> list[Finding]:
    """SP001, SP002, SP080 (approval record) and SP081 (PRD version)."""
    h = spec.header
    out = [finding("SP001", spec.id or "spec", f"no '{k}:' line") for k in REQUIRED_HEADER if not h.get(k)]
    if h.get("Version") and not SEMVER.match(h["Version"]):
        out.append(finding("SP002", spec.id, f"version {h['Version']!r}"))
    approvers = {a.strip() for a in h.get("Approved by", "").split(",") if a.strip()}
    needed = [h.get("Product owner"), h.get("Tech lead")]
    if h.get("Risk") == "high":
        needed.append(h.get("Security reviewer"))
        if not h.get("Security reviewer"):
            out.append(finding("SP080", spec.id, "Risk: high needs a 'Security reviewer:' line"))
    missing = [n for n in needed if n and n not in approvers]
    if h.get("Status") != "approved" or missing or not h.get("Approved on"):
        why = [] if h.get("Status") == "approved" else [f"status is {h.get('Status') or '(none)'!r}"]
        why += [f"{m} has not approved" for m in missing]
        why += [] if h.get("Approved on") else ["no approval date"]
        out.append(finding("SP080", spec.id, "; ".join(why)))
    derived = h.get("Derived from", "")
    if derived and not derived.endswith(f"@{prd.version}"):
        out.append(finding("SP081", spec.id, f"derived from {derived!r}; the PRD given is version {prd.version}"))
    return out


def check_criteria(spec: Spec, prd: Prd) -> list[Finding]:
    """SP020-SP023: each criterion is the PRD's, word for word, under the PRD's requirement."""
    out = []
    for c in spec.criteria:
        if c.id not in prd.criteria:
            out.append(finding("SP020", c.id, "not a criterion of the PRD"))
            continue
        requirement, text = prd.criteria[c.id]
        if c.text != text:
            out.append(finding("SP021", c.id, "text differs from the PRD; change the PRD first, then the spec"))
        if c.requirement != requirement:
            out.append(finding("SP022", c.id, f"spec says {c.requirement or '(none)'}, the PRD says {requirement}"))
        if c.coverage not in ("full", "partial") or (c.coverage == "partial" and not c.deferred):
            out.append(finding("SP023", c.id, f"coverage {c.coverage or '(none)'!r}"
                               + (" with nothing deferred" if c.coverage == "partial" else "")))
    return out


def check_constraints(spec: Spec, tests: tuple[str, ...]) -> list[Finding]:
    """SP072: each security constraint has a source and a check; SP032: named policy tests exist."""
    out = []
    for c in spec.constraints:
        if not c.sources or not c.checks:
            out.append(finding("SP072", c.id, "needs both a Source: and a Checks: line"))
        for check in c.checks:
            if check.startswith("test_") and not any(t.startswith(check) for t in tests):
                out.append(finding("SP032", c.id, f"no test named {check}..."))
    return out


def check_contract(spec: Spec, contract: Contract | None) -> list[Finding]:
    """SP070, SP071, and SP062: outbound documents carry only Public or Internal fields."""
    if contract is None:
        return [finding("SP070", spec.contract_path or "Contracts", "no readable contract file")]
    out = []
    if not contract.definitions:
        out.append(finding("SP070", spec.contract_path, "the contract defines no documents"))
    if contract.version != spec.version:
        out.append(finding("SP071", spec.contract_path, f"contract {contract.version or '(none)'}, "
                                                        f"spec {spec.version}"))
    for name in spec.outbound:
        for f in contract.definitions.get(name, {}):
            cls = spec.data_rules.get(f"{name}.{f}")
            if cls in ("Confidential", "Restricted"):
                out.append(finding("SP062", f"{name}.{f}", f"{cls} field in an outbound document"))
    return out


def check_task_fields(spec: Spec, tasks: TaskList) -> list[Finding]:
    """SP082 (spec reference), SP043 (dependencies), SP044 (size), SP045 (labels)."""
    out = []
    if tasks.spec_ref != f"{spec.id}@{spec.version}":
        out.append(finding("SP082", "tasks", f"tasks are for {tasks.spec_ref or '(none)'}, "
                                             f"the spec is {spec.id}@{spec.version}"))
    ids = {t.id for t in tasks.tasks}
    for t in tasks.tasks:
        for d in t.depends:
            if d not in ids:
                out.append(finding("SP043", t.id, f"depends on unknown task {d}"))
        if len(t.checks) > MAX_TASK_CHECKS or len(t.files) > MAX_TASK_FILES:
            out.append(finding("SP044", t.id, f"{len(t.checks)} check(s), {len(t.files)} file(s); consider splitting"))
        bad = [n for n, v, ok in (("Risk", t.risk, RISKS), ("Sensitive", t.sensitive, ("yes", "no")),
                                  ("Untrusted input", t.untrusted, ("yes", "no"))) if v not in ok]
        if bad:
            out.append(finding("SP045", t.id, f"invalid or missing: {', '.join(bad)}"))
    from .plan import find_cycle
    cycle = find_cycle(tasks)
    if cycle:
        out.append(finding("SP043", cycle[0], "dependency cycle: " + " -> ".join(cycle)))
    return out


@dataclass(frozen=True)
class Result:
    spec: Spec
    tasks: TaskList
    contract: Contract | None
    tests: tuple[str, ...]
    findings: tuple[Finding, ...]


def run_checks(spec_dir: Path, prd: Prd, tests: tuple[str, ...], tasks_file: Path | None = None) -> Result:
    """Every check on one spec package. `tasks_file` replaces the package's tasks.md if given."""
    spec = load_spec(spec_dir)
    tasks = load_tasks(Path(tasks_file) if tasks_file else Path(spec_dir) / "tasks.md")
    contract = load_contract(spec)
    found = (check_header(spec, prd) + check_sections(spec) + check_criteria(spec, prd) + check_tests(spec, tests)
             + check_constraints(spec, tests) + check_task_fields(spec, tasks) + check_task_links(spec, tasks)
             + check_tiers(tasks) + check_classification(spec, contract) + check_contract(spec, contract))
    return Result(spec, tasks, contract, tests, tuple(found))


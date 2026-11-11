"""The maintenance policy, protected paths, code owners and triage from structured fields (4.31.0, ADR-053, ADR-056).

Report bodies here are inert placeholders: a labelled record stands where an attacker's text would be, and no
test contains working injection text."""

import copy
import json

import pytest

from maintenance_helpers import OWNERS, POLICY, ROOT
from relay.maintenance import Report, approver_problem, metrics, triage, validate

DATA = json.loads((ROOT / "maintenance" / "policy.json").read_text(encoding="utf-8"))
INERT = "[[INERT-INJECTION-PLACEHOLDER asks-for: protected-edit, self-approval]]"


def test_the_committed_policy_loads_and_grants_nothing_above_t2():
    assert validate(DATA) == []
    assert {t.tier for t in POLICY.task_types.values()} <= {"T1", "T2"}
    assert all(not t.self_modification and t.autonomy_grant is None for t in POLICY.task_types.values())


@pytest.mark.parametrize("path", ["AGENTS.md", ".github/workflows/maintenance.yml", ".github/CODEOWNERS",
                                  "governance/agents.json", "maintenance/policy.json",
                                  "src/relay/maintenance/proposals.py", "src/relay/agents/boundary.py",
                                  "tests/test_maintenance_policy.py", "tests/maintenance_helpers.py",
                                  "supply-chain/mirror.json", "security/gates.json", "tools/supplychain.py",
                                  "docs/adr/ADR-053-maintenance-bot-design.md", "docs/slo/slos.json"])
def test_the_bot_can_never_write_its_own_instructions_workflow_policy_code_or_checks(path):
    assert POLICY.protected(path)
    assert not any(POLICY.writable(t, path) for t in POLICY.task_types)


def test_each_task_type_writes_only_its_own_paths():
    assert POLICY.writable("docs-upkeep", "docs/integrations.md")
    assert not POLICY.writable("docs-upkeep", "docs/adr/ADR-010-business-hours-time-zones.md")
    assert POLICY.writable("dependency-update", "deploy/requirements.txt")
    assert not POLICY.writable("dependency-update", "src/relay/store.py")
    assert POLICY.writable("table-extension", "src/relay/escalation/hours.py")
    assert not POLICY.writable("bug-reproduction", "tests/test_store.py")
    for bad in ("../AGENTS.md", "docs/../AGENTS.md", "/docs/x.md", "docs\\x.md", "C:docs/x.md"):
        assert not POLICY.writable("docs-upkeep", bad)


@pytest.mark.parametrize("change,problem", [
    (lambda d: d["task_types"]["docs-upkeep"].update(tier="T4"), "T4 needs an autonomy grant"),
    (lambda d: d["task_types"]["docs-upkeep"].update(tier="T3"), "T3 needs an autonomy grant"),
    (lambda d: d["task_types"]["docs-upkeep"].update(write_paths=["maintenance/"]), "inside a protected path"),
    (lambda d: d["task_types"]["docs-upkeep"].update(self_modification=True), "self-modifying task types"),
    (lambda d: d["protected_paths"].remove("maintenance/"), "must include maintenance/"),
    (lambda d: d["task_types"]["docs-upkeep"].update(approval_teams=[]), "names no approval team"),
    (lambda d: d.update(bot_owner="maintenance-bot"), "bot_owner must be a person"),
])
def test_unsafe_policies_are_refused(change, problem):
    d = copy.deepcopy(DATA)
    change(d)
    assert any(problem in p for p in validate(d)), validate(d)


def test_chapter_12s_cap_t3_for_an_untrusted_reader_needs_a_report_with_a4_passed():
    for flag in (True, None):
        d = copy.deepcopy(DATA)
        d["task_types"]["docs-upkeep"].update(tier="T3")
        if flag is None:
            d["task_types"]["docs-upkeep"].pop("reads_untrusted")
        assert any("T3 needs an autonomy grant" in p for p in validate(d, ROOT))
    d = copy.deepcopy(DATA)
    d["task_types"]["table-extension"].update(tier="T3")      # reads nothing untrusted: T3 needs no grant
    assert validate(d, ROOT) == []


def test_a_typed_grant_is_refused_whatever_names_it_carries():
    d = copy.deepcopy(DATA)
    d["task_types"]["docs-upkeep"].update(tier="T4", autonomy_grant={"eligibility": "pass", "approvals": [
        {"by": "aisha.r"}, {"by": "sam.o"}]})
    assert any("the grant types approvals, eligibility" in p for p in validate(d, ROOT))


def _report(log, evidence):
    from relay.maintenance.autonomy import eligibility_report
    return eligibility_report("docs-upkeep", metrics(log, "docs-upkeep"), True, evidence, "2027-07-09")


def _granted(tmp_path, log, evidence, tier="T4", report=None, sha=None):
    """Commit an outcome log, an evidence file and a report under maintenance/eligibility/, and a grant naming them."""
    import hashlib
    folder = tmp_path / "maintenance" / "eligibility"
    folder.mkdir(parents=True)
    raw = json.dumps(report or _report(log, evidence), sort_keys=True).encode("utf-8")
    (folder / "docs-upkeep.json").write_bytes(raw)
    (folder / "docs-upkeep-outcomes.json").write_text(json.dumps(log), encoding="utf-8")
    (folder / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    d = copy.deepcopy(DATA)
    d["task_types"]["docs-upkeep"].update(tier=tier, autonomy_grant={
        "report": "maintenance/eligibility/docs-upkeep.json", "report_sha256": sha or hashlib.sha256(raw).hexdigest(),
        "outcomes": "maintenance/eligibility/docs-upkeep-outcomes.json",
        "evidence": "maintenance/eligibility/evidence.json", "as_of": "2027-07-09"})
    return d


CLEAN = [{"task_type": "docs-upkeep", "outcome": "merged", "usd": 0.04} for _ in range(80)]
DRILL = {"on": "2027-06-30", "status": "deployed", "record": "drill log"}
ALL = {"coverage_gate": "pass", "live_attack_measurement": {"owner": "aisha.r"}, "killswitch_drill": DRILL,
       "rollback_drill": DRILL, "scan_catch_rate": [83, 100]}


def test_a_grant_loads_only_with_the_report_recomputed_from_its_log_and_every_criterion_passed(tmp_path):
    assert validate(_granted(tmp_path, CLEAN, ALL), tmp_path) == []
    assert validate(_granted(tmp_path / "x", CLEAN, ALL), None)[0].endswith("(no repository root)")
    tampered = _granted(tmp_path / "t", CLEAN, ALL, sha="0" * 64)
    assert any("does not match the grant's hash" in p for p in validate(tampered, tmp_path / "t"))
    no_a4 = {**ALL, "live_attack_measurement": None}
    assert any("Chapter 12's T2 cap holds" in p for p in validate(_granted(tmp_path / "a", CLEAN, no_a4, "T3"),
                                                                    tmp_path / "a"))
    small = CLEAN[:12]
    assert any("failed or missing: A1" in p for p in validate(_granted(tmp_path / "s", small, ALL), tmp_path / "s"))


def test_a_hand_written_report_is_refused_even_with_its_hash(tmp_path):
    """Editor's probe F1: every criterion typed as passed, over a log of 12 changes. The loader recomputes it."""
    forged = _report(CLEAN[:12], ALL)
    forged["criteria"] = [{**c, "passed": True} for c in forged["criteria"]]
    forged["verdict"] = "candidate for a grant"
    d = _granted(tmp_path, CLEAN[:12], ALL, report=forged)
    assert any("is not the one recomputed from the outcome log and evidence" in p for p in validate(d, tmp_path))


def test_reads_untrusted_is_derived_from_the_task_types_inputs():
    """Editor's probe F2: declaring an issue-driven task type trusted does not lift the T2 cap."""
    d = copy.deepcopy(DATA)
    d["task_types"]["docs-upkeep"].update(reads_untrusted=False, tier="T3")
    problems = validate(d, ROOT)
    assert any("reads_untrusted is derived" in p for p in problems)
    assert any("T3 needs an autonomy grant" in p for p in problems)
    assert POLICY.task("table-extension").reads_untrusted is False and POLICY.task("docs-upkeep").reads_untrusted


def test_a_self_modifying_task_type_never_loads():
    d = copy.deepcopy(DATA)
    d["task_types"]["docs-upkeep"].update(self_modification=True, safety_case="any")
    assert any("self-modifying task types are refused" in p for p in validate(d, ROOT))


def test_protected_paths_are_compared_case_folded():
    assert POLICY.protected("docs/ADR/ADR-099.md") and not POLICY.writable("docs-upkeep", "docs/ADR/ADR-099.md")
    assert POLICY.protected("Agents.md") and POLICY.protected(".GitHub/workflows/x.yml")


def test_codeowners_last_match_wins():
    assert OWNERS.owners("deploy/requirements.txt") == ("@relay/security",)
    assert OWNERS.owners("docs/integrations.md") == ("@relay/maintainers",)
    assert OWNERS.owners("src/relay/escalation/hours.py") == ("@relay/maintainers",)
    assert set(OWNERS.owners("maintenance/policy.json")) == {"@relay/security", "@relay/platform-leads"}


@pytest.mark.parametrize("person,task,paths,packages,problem", [
    ("priya.n", "docs-upkeep", ["docs/integrations.md"], [], "bot_owner_may_not_approve"),
    ("lena.k", "docs-upkeep", ["docs/integrations.md"], [], "not_a_code_owner:docs/integrations.md"),
    ("sam.o", "docs-upkeep", ["docs/integrations.md"], [], None),
    ("sam.o", "dependency-update", ["deploy/requirements.txt"], ["gunicorn"],
     "not_a_code_owner:deploy/requirements.txt"),
    ("aisha.r", "dependency-update", ["deploy/requirements.txt"], ["gunicorn"], None),
    ("sam.o", "table-extension", ["src/relay/escalation/hours.py"], [], None),
    ("aisha.r", "table-extension", ["src/relay/escalation/hours.py"], [],
     "not_a_code_owner:src/relay/escalation/hours.py"),
])
def test_who_may_approve_comes_from_the_paths_and_the_task_type(person, task, paths, packages, problem):
    assert approver_problem(POLICY, OWNERS, person, task, paths, packages) == problem


LOCK = {"sessionkeel": "2.4.1", "gunicorn": "23.0.0"}


def test_an_advisory_becomes_a_fix_task_from_its_fields_only():
    r = Report("ADV-1", "advisory-feed", {"package": "sessionkeel", "fixed": "2.4.2",
                                          "advisory": "LAB-ADV-2027-0113"}, body=INERT)
    t = triage(r, LOCK)
    assert (t.task_type, t.untrusted, t.fields["locked"]) == ("vulnerability-fix", True, "2.4.1")


@pytest.mark.parametrize("form,reason", [
    ({"package": "Sessionkeel; rm", "fixed": "2.4.2", "advisory": "LAB-ADV-2027-0113"}, "malformed_advisory"),
    ({"package": "sessionkeel", "fixed": "latest", "advisory": "LAB-ADV-2027-0113"}, "malformed_advisory"),
    ({"package": "tallowcsv", "fixed": "1.0.0", "advisory": "LAB-ADV-2027-0114"}, "not_ours"),
])
def test_a_malformed_or_foreign_advisory_goes_to_a_person(form, reason):
    assert triage(Report("ADV-2", "advisory-feed", form), LOCK).reason == reason


def test_the_body_never_changes_the_task_type():
    plain = Report("ISS-1", "issue-form", {"component": "docs", "kind": "broken-link"}, body="link 404s")
    steered = Report("ISS-1", "issue-form", {"component": "docs", "kind": "broken-link"}, body=INERT)
    assert triage(plain, LOCK) == triage(steered, LOCK)
    assert triage(Report("ISS-2", "issue-form", {"kind": "bug"}, body=INERT), LOCK).task_type is None


def test_unknown_sources_are_untrusted_and_go_to_a_person():
    t = triage(Report("SUP-1", "support-sync", {"job": "dependency-refresh"}), LOCK)
    assert t.task_type is None and t.untrusted
    assert triage(Report("X", "mystery", {}), LOCK).reason == "unknown_source_or_id"
    assert triage(Report("S-1", "schedule", {"job": "dst-table"}), LOCK).task_type == "table-extension"

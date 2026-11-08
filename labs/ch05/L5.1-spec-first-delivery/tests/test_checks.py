"""The five TODO checks, on inputs small enough to check by hand."""

from pathlib import Path

from speccheck.checks import check_classification, check_sections, check_task_links, check_tests, check_tiers
from speccheck.core import REQUIRED_SECTIONS
from speccheck.spec import Constraint, Contract, Criterion, Spec, Task, TaskList


def spec(sections=None, criteria=("ESC-AC08", "ESC-AC10"), constraints=("SEC-01",), data_rules=None):
    if sections is None:
        sections = {name: "Some text.\n" for name in REQUIRED_SECTIONS}
    return Spec(Path("spec.md"), {}, sections,
                tuple(Criterion(c, "ESC-R04", "full", "Given ...", "") for c in criteria),
                tuple(Constraint(c, "", ("ESC-N05",), ("ESC-AC24",), "") for c in constraints),
                data_rules or {}, None, (), (), ())


def task(tid, checks=("ESC-AC08",), tier="T2", sensitive="no", untrusted="no"):
    return Task(tid, f"task {tid}", tuple(checks), (), (), "medium", sensitive, untrusted, tier, "")


def tasks(*items):
    return TaskList(Path("tasks.md"), "ESC-SPEC-1@1.0.0", tuple(items))


def codes(findings):
    return [(f.code, f.item) for f in findings]


# ------------------------------------------------------------------ check_sections

def test_sections_complete():
    assert check_sections(spec()) == []


def test_sections_missing_empty_and_to_complete():
    sections = {name: "Text.\n" for name in REQUIRED_SECTIONS}
    del sections["Non-goals"]
    sections["Data rules"] = "  \n\n"
    sections["Security constraints"] = "Status: TO COMPLETE.\n"
    assert codes(check_sections(spec(sections))) == [
        ("SP010", "Non-goals"), ("SP011", "Data rules"), ("SP011", "Security constraints")]


def test_sections_reported_in_required_order():
    found = check_sections(spec({}))
    assert [f.item for f in found] == list(REQUIRED_SECTIONS) and {f.code for f in found} == {"SP010"}


# ------------------------------------------------------------------ check_tests

def test_every_criterion_tested():
    names = ("test_ESC_AC08_first_step", "test_ESC_AC08_boundary", "test_ESC_AC10", "test_helper")
    assert check_tests(spec(), names) == []


def test_untested_criterion_and_unknown_test():
    names = ("test_ESC_AC08_first_step", "test_ESC_AC12_business_hours", "test_ESC_AC12_weekend",
             "test_ESC_AC100_typo", "test_ESC_AC080_is_not_ac08")
    found = check_tests(spec(), names)
    assert codes(found) == [("SP030", "ESC-AC10"), ("SP031", "ESC-AC080"), ("SP031", "ESC-AC100"),
                            ("SP031", "ESC-AC12")]
    assert "test_ESC_AC12_business_hours" in found[3].message and "test_ESC_AC12_weekend" in found[3].message


def test_name_must_carry_the_id_exactly():
    # test_ESC_AC08x does not name ESC-AC08: the ID must end the name or be followed by "_"
    assert codes(check_tests(spec(criteria=("ESC-AC08",)), ("test_ESC_AC08x",))) == [("SP030", "ESC-AC08")]


# ------------------------------------------------------------------ check_task_links

def test_tasks_cover_everything():
    plan = tasks(task("T01", ("ESC-AC08", "SEC-01")), task("T02", ("ESC-AC10",)))
    assert check_task_links(spec(), plan) == []


def test_task_links_all_three_findings():
    plan = tasks(task("T01", ("ESC-AC08", "ESC-AC12", "SEC-09")), task("T02", ()))
    assert codes(check_task_links(spec(), plan)) == [
        ("SP041", "T01"), ("SP041", "T01"), ("SP040", "T02"), ("SP042", "ESC-AC10"), ("SP042", "SEC-01")]


def test_unknown_id_is_named():
    found = check_task_links(spec(criteria=("ESC-AC08",), constraints=()), tasks(task("T01", ("ESC-AC08", "ESC-AC12"))))
    assert codes(found) == [("SP041", "T01")] and "ESC-AC12" in found[0].message


# ------------------------------------------------------------------ check_tiers

def test_tiers_within_caps():
    plan = tasks(task("T01", tier="T2", untrusted="yes"), task("T02", tier="T3", sensitive="yes"),
                 task("T03", tier="T4"), task("T04", tier="T0", untrusted="yes", sensitive="yes"))
    assert check_tiers(plan) == []


def test_tier_findings():
    plan = tasks(task("T01", tier=""), task("T02", tier="T5"), task("T03", tier="T3", untrusted="yes"),
                 task("T04", tier="T4", sensitive="yes"), task("T05", tier="T4", untrusted="yes", sensitive="yes"))
    assert codes(check_tiers(plan)) == [("SP050", "T01"), ("SP050", "T02"), ("SP051", "T03"), ("SP052", "T04"),
                                        ("SP051", "T05")]


# ------------------------------------------------------------------ check_classification

CONTRACT = Contract(Path("c.json"), "1.0.0", {"Rule": {"rule_id": {}, "steps": {}}, "Evaluation": {"task_id": {}}})


def test_every_contract_field_classified():
    rules = {"Rule.rule_id": "Internal", "Rule.steps": "Internal", "Evaluation.task_id": "Internal",
             "Task.title": "Confidential"}
    assert check_classification(spec(data_rules=rules), CONTRACT) == []


def test_no_data_rules_is_one_finding():
    assert codes(check_classification(spec(data_rules={}), CONTRACT)) == [("SP060", "Data rules")]


def test_unclassified_and_unknown_classes():
    rules = {"Rule.rule_id": "Secret", "Evaluation.task_id": "internal", "Task.title": "Confidential"}
    assert codes(check_classification(spec(data_rules=rules), CONTRACT)) == [
        ("SP061", "Rule.rule_id"), ("SP061", "Evaluation.task_id"), ("SP060", "Rule.steps")]


def test_no_contract_checks_only_the_table():
    assert codes(check_classification(spec(data_rules={"Task.title": "Public"}), None)) == []

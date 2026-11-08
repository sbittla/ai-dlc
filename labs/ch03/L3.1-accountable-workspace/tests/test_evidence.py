"""The evidence-record checker (provided code; these tests pass before you start)."""

from conftest import FIXTURES, LAB_ROOT

from audit import evidence


def test_blank_template_lists_every_missing_field():
    found = evidence.problems((LAB_ROOT / "templates" / "evidence-record.yaml").read_text(encoding="utf-8"))
    assert [p for p in found if p.startswith("field")] == [
        f"field '{k}' is missing or blank" for k in evidence.REQUIRED_FIELDS]


def test_complete_record_has_no_problems():
    assert evidence.problems((FIXTURES / "evidence-good.yaml").read_text(encoding="utf-8")) == []


def test_self_approval_is_rejected():
    text = (FIXTURES / "evidence-good.yaml").read_text(encoding="utf-8").replace("accepted_by: sam.o",
                                                                                   "accepted_by: priya.n")
    assert evidence.problems(text) == ["accepted_by is the author of record: nobody approves their own change"]


def test_missing_failing_test_check_is_reported():
    text = (FIXTURES / "evidence-good.yaml").read_text(encoding="utf-8").replace("failing test first", "unit tests")
    assert evidence.problems(text) == ["no check named like 'failing test'"]

"""Your test-first files, graded: written from the spec, failing for the right reason, catching every seeded bug.

Until you replace the stubs in relay-repo/tests/escalation/ (README steps 2 and 3),
these tests stop with NotImplementedError.
"""

import pytest
from conftest import DATA_DIR, LAB_ROOT, RELAY_REPO

from testfirst.grade import grade


@pytest.fixture(scope="module")
def result():
    g = grade(RELAY_REPO, LAB_ROOT / "starter" / "relay-repo", DATA_DIR)
    if not all(g.written.values()):
        missing = [g.files[k] for k, v in g.written.items() if not v]
        raise NotImplementedError(f"write the test-first tests first (README steps 2 and 3): {missing}")
    return g


def test_every_required_criterion_has_a_test_named_after_it(result):
    assert result.named == {"hours": [], "delivery": []}


@pytest.mark.parametrize("group", ["hours", "delivery"])
def test_every_test_fails_on_the_stubs_for_the_right_reason(result, group):
    right, total, early, wrong = result.right_reason(group)
    assert early == [], f"these pass before the code exists, so they test nothing new: {early}"
    assert wrong == [], f"these fail for a reason other than the missing code: {wrong}"
    assert right == total > 0


def test_every_test_passes_on_the_reference_implementation(result):
    assert [r.test for r in result.reference.failed()] == []


@pytest.mark.parametrize("variant", ["H1-utc-windows", "H2-close-rolls-over", "H3-weekends-count",
                                     "H4-no-daylight-saving", "H5-counts-before-opening", "D1-title-in-subject",
                                     "D2-signs-other-bytes", "D3-event-per-target", "D4-project-link"])
def test_each_seeded_bug_makes_at_least_one_test_fail(result, variant):
    [(v, run)] = [(v, r) for v, r in result.bugs if v["id"] == variant]
    assert result.killed(v, run), f"no test in {result.files[v['group']]} catches {variant}: {v['description']}"


def test_no_expected_value_comes_from_the_code_under_test(result):
    assert [f.row() for f in result.findings if f.blocking] == []

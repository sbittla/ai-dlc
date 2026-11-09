"""The pull-request check, rule by rule, on small records you can check by hand (prkit.prcheck.check_pr)."""

import pytest

from prkit import codeowners, prcheck


def f(path, status="M", added=1, removed=0, added_lines=(), removed_lines=()):
    return {"path": path, "status": status, "added": added, "removed": removed,
            "added_lines": list(added_lines), "removed_lines": list(removed_lines)}


def pr(*commits, minutes=30, description="Docs: spec B8."):
    return {"id": "T", "review": {"minutes": minutes}, "description": description,
            "commits": [{"author": "x", "message": "m", "files": list(c)} for c in commits]}


TESTS_FIRST = [f("tests/test_new.py", "A", 20)]


def codes(record):
    return [x.code for x in prcheck.check_pr(record)]


def test_a_small_tests_first_pull_request_has_no_findings():
    assert codes(pr(TESTS_FIRST, [f("src/relay/x.py", "M", 10, 2)])) == []


@pytest.mark.parametrize("code_lines, test_lines, expected", [
    (200, 200, []),           # exactly at both limits
    (201, 0, ["PR01"]),       # one line too many outside tests/
    (150, 251, ["PR01"]),     # 401 in all
])
def test_PR01_size_limits(code_lines, test_lines, expected):
    record = pr([f("tests/test_new.py", "A", test_lines)], [f("src/relay/x.py", "M", code_lines)], minutes=120)
    assert codes(record) == expected


def test_PR02_an_existing_test_changed_with_the_code_but_a_new_test_file_is_fine():
    assert codes(pr(TESTS_FIRST, [f("src/relay/x.py"), f("tests/test_old.py", "M")])) == ["PR02"]
    assert codes(pr(TESTS_FIRST, [f("src/relay/x.py"), f("tests/test_other_new.py", "A")])) == []


def test_PR03_code_needs_a_tests_only_commit_before_it():
    assert codes(pr([f("src/relay/x.py")], TESTS_FIRST)) == ["PR03"]
    assert codes(pr([f("docs/adr/ADR-1.md", "A")], [f("src/relay/x.py")])) == ["PR03"]


def test_PR04_a_migration_needs_a_migration_test():
    drop = f("src/relay/x/store.py", "M", 2, 0, added_lines=["    conn.execute('DROP TABLE old')"])
    assert codes(pr(TESTS_FIRST, [drop])) == ["PR04"]
    assert codes(pr([f("tests/test_x_migrations.py", "A")], [drop])) == []
    assert codes(pr(TESTS_FIRST, [f("migrations/0042_x.py", "A")])) == ["PR04"]


def test_PR05_a_new_route_needs_its_openapi_description():
    route = f("src/relay/service/routes.py", added_lines=['    ("DELETE", "/v1/projects/{pid}/x"),'])
    assert codes(pr(TESTS_FIRST, [route])) == ["PR05"]
    assert codes(pr(TESTS_FIRST, [route, f("specs/1/contracts/x-api.openapi.json")])) == []


def test_PR06_the_spec_and_code_in_one_pull_request():
    assert codes(pr(TESTS_FIRST, [f("src/relay/x.py"), f("specs/001-x/spec.md")])) == ["PR06"]
    assert codes(pr([f("specs/001-x/spec.md")])) == []


def test_PR07_oracle_markers_and_properties_are_listed_for_review_as_warnings():
    marked = f("tests/test_x.py", "M", 1, 1, added_lines=["    assert g(x) == g(x)  # oracle: invariance - why"])
    prop = f("tests/test_y.py", "M", 1, 0, added_lines=["@for_all(INTS)"])
    found = prcheck.check_pr(pr([marked, prop]))
    assert [(x.code, x.blocking) for x in found] == [("PR07", False)]
    assert "tests/test_x.py, tests/test_y.py" in found[0].message


def test_PR08_review_rate_over_500_lines_an_hour():
    at_limit = pr([f("tests/test_new.py", "A", 70)], [f("src/relay/x.py", "M", 180)], minutes=30)  # 250 in 30 min
    over = pr([f("tests/test_new.py", "A", 71)], [f("src/relay/x.py", "M", 180)], minutes=30)
    assert (codes(at_limit), codes(over)) == ([], ["PR08"])


def test_PR09_code_without_docs_or_a_docs_line():
    assert codes(pr(TESTS_FIRST, [f("src/relay/x.py")], description="Refactor.")) == ["PR09"]
    assert codes(pr(TESTS_FIRST, [f("src/relay/x.py"), f("docs/adr/ADR-9.md", "A")], description="")) == []


def test_codeowners_last_match_wins_and_unknown_patterns_are_refused():
    rules = codeowners.parse("*  @team/all\n/tests/  @team/qa\n/tests/test_x.py  @team/sec\n")
    assert codeowners.owners_for(rules, "src/a.py") == ("@team/all",)
    assert codeowners.owners_for(rules, "tests/test_y.py") == ("@team/qa",)
    assert codeowners.owners_for(rules, "tests/test_x.py") == ("@team/sec",)
    with pytest.raises(ValueError):
        codeowners.parse("*.py @team/all\n")


def test_PR10_a_pull_request_needs_a_reviewer_who_neither_opened_it_nor_wrote_a_commit():
    def rec(reviewers, opened_by="priya.n"):
        r = pr([f("tests/test_new.py", "A", 20)], [f("src/relay/x.py")])
        r["commits"][0]["author"], r["commits"][1]["author"] = "aisha.r", "agent (priya.n)"
        r["opened_by"], r["review"]["reviewers"] = opened_by, reviewers
        return r

    assert codes(rec(["aisha.r"])) == ["PR10"]           # wrote the tests
    assert codes(rec(["priya.n"])) == ["PR10"]           # ran the agent that wrote the code, and opened it
    assert codes(rec(["sam.o"], opened_by="sam.o")) == ["PR10"]
    assert codes(rec(["aisha.r", "sam.o"])) == []        # sam.o is independent

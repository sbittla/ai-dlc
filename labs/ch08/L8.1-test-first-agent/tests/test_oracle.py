"""The oracle-independence check (testfirst.oracle), on small test files you can check by hand."""

from testfirst.oracle import check_oracles, tainted_names

import ast

MODULES = ("relay.escalation",)
HEADER = "from relay.escalation import add_business_minutes, sign, event_body\nimport hmac\n\n"


def codes(body: str) -> list[tuple[str, str]]:
    return [(f.code, f.test) for f in check_oracles(HEADER + body, "t.py", MODULES)]


def test_a_literal_expected_value_is_independent():
    assert codes("def test_a():\n    assert add_business_minutes(1, 2, 3) == 42\n") == []


def test_comparing_the_code_with_itself_is_OI01():
    assert codes("def test_a():\n    assert sign(b, k) == sign(event_body(e), k)\n") == [("OI01", "test_a")]


def test_an_expected_value_assigned_from_the_code_is_OI01():
    body = ("def test_a():\n    expected = add_business_minutes(s, 30, h) + 30\n"
            "    assert add_business_minutes(s, 60, h) == expected\n")
    assert codes(body) == [("OI01", "test_a")]


def test_taint_follows_names_through_several_assignments():
    tree = ast.parse("def test_a():\n    a = add_business_minutes(1, 2, 3)\n    b = a.date\n    c = b + 1\n    d = 5\n")
    assert tainted_names(tree.body[0], {"add_business_minutes"}) == {"a", "b", "c"}


def test_recomputing_with_an_independent_function_is_allowed():
    body = ("def test_a():\n    body = event_body(e)\n    expected = 'sha256=' + hmac.new(k, body, h).hexdigest()\n"
            "    assert sign(body, k) == expected\n")
    assert codes(body) == []


def test_a_helper_that_calls_the_code_counts_as_the_code():
    body = ("def due(s):\n    return add_business_minutes(s, 30, None)\n\n"
            "def test_a():\n    assert add_business_minutes(s, 30, None) == due(s)\n")
    assert codes(body) == [("OI01", "test_a")]


def test_a_test_with_no_assertion_is_OI02_and_pytest_raises_counts():
    body = ("def test_a():\n    sign(b, k)\n\n"
            "def test_b():\n    with pytest.raises(ValueError):\n        sign(b, k)\n")
    assert codes(body) == [("OI02", "test_a")]


def test_existence_checks_are_OI03():
    body = ("def test_a():\n    assert add_business_minutes(s, 1, h) is not None\n\n"
            "def test_b():\n    r = add_business_minutes(s, 1, h)\n    assert r\n\n"
            "def test_c():\n    assert len(sign(b, k))\n")
    assert codes(body) == [("OI03", "test_a"), ("OI03", "test_b"), ("OI03", "test_c")]


def test_only_imports_from_the_modules_under_test_count():
    body = "from datetime import datetime\n\ndef test_a():\n    assert datetime(2026, 1, 1) == datetime(2026, 1, 1)\n"
    assert codes(body) == []


def test_findings_name_the_line():
    [finding] = check_oracles(HEADER + "def test_a():\n    x = 1\n    assert sign(b, k) == sign(b, k)\n", "t.py",
                              MODULES)
    assert (finding.code, finding.line, finding.blocking) == ("OI01", 6, True)

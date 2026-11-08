"""The four TODO comparisons, on facts small enough to check by hand."""

from driftcheck.compare import compare_criteria, compare_enums, compare_fields, compare_versions
from driftcheck.extract import Facts


def codes(found):
    return [(d.code, d.item) for d in found]


# ------------------------------------------------------------------ compare_versions

def test_versions_agree():
    facts = Facts(spec_version="1.0.0", contract_version="1.0.0", code_version="1.0.0",
                  test_versions={"test_a.py": "1.0.0"})
    assert compare_versions(facts) == []


def test_one_finding_listing_every_source():
    facts = Facts(spec_version="1.1.0", contract_version="1.0.0", code_version="1.0.0",
                  test_versions={"test_b.py": "1.0.0", "test_a.py": ""})
    found = compare_versions(facts)
    assert codes(found) == [("DR001", "version")]
    assert found[0].message == "spec 1.1.0, contract 1.0.0, code 1.0.0, test_a.py missing, test_b.py 1.0.0"


# ------------------------------------------------------------------ compare_fields

def test_fields_agree():
    facts = Facts(contract_fields={"Step.number": "integer"}, code_fields={"Step.number": "integer"},
                  data_rules={"Step.number": "Internal"})
    assert compare_fields(facts) == []


def test_field_drift_in_order():
    facts = Facts(contract_fields={"Step.delay_minutes": "integer", "Step.number": "integer",
                                   "Rule.steps": "array"},
                  code_fields={"Step.delay_seconds": "integer", "Step.number": "number", "Rule.steps": "array"},
                  data_rules={"Step.number": "Internal"})
    assert codes(compare_fields(facts)) == [
        ("DR010", "Step.delay_minutes"), ("DR011", "Step.delay_seconds"), ("DR012", "Step.number"),
        ("DR013", "Rule.steps"), ("DR013", "Step.delay_minutes")]


def test_type_message_names_both():
    facts = Facts(contract_fields={"Step.number": "integer"}, code_fields={"Step.number": "number"},
                  data_rules={"Step.number": "Internal"})
    assert compare_fields(facts)[0].message == "contract integer, code number"


# ------------------------------------------------------------------ compare_enums

def test_enums_agree_as_sets():
    facts = Facts(contract_enums={"STATUSES": ("a", "b"), "PRIORITIES": ("P1",)},
                  code_constants={"STATUSES": ("b", "a"), "PRIORITIES": ("P1",)},
                  spec_tables={"Status": ("a", "b")})
    assert compare_enums(facts) == []


def test_enum_drift():
    facts = Facts(contract_enums={"STATUSES": ("a", "b"), "ERROR_CODES": ("x",), "PRIORITIES": ("P1", "P2")},
                  code_constants={"STATUSES": ("a", "b", "snoozed"), "ERROR_CODES": ("x",)},
                  spec_tables={"Status": ("a",)})
    found = compare_enums(facts)
    # sorted by constant name: ERROR_CODES, PRIORITIES, STATUSES; no "Code" table in the spec
    assert codes(found) == [("DR021", "ERROR_CODES"), ("DR020", "PRIORITIES"), ("DR020", "STATUSES"),
                            ("DR021", "STATUSES")]
    assert "snoozed" in found[2].message


# ------------------------------------------------------------------ compare_criteria

def test_criteria_agree():
    facts = Facts(criteria=("ESC-AC08",), tested={"ESC-AC08": ("test_ESC_AC08_a", "test_ESC_AC08_b")})
    assert compare_criteria(facts) == []


def test_criteria_drift():
    facts = Facts(criteria=("ESC-AC12", "ESC-AC08"), tested={"ESC-AC08": ("t1",), "ESC-AC15": ("test_ESC_AC15_x",)})
    found = compare_criteria(facts)
    assert codes(found) == [("DR030", "ESC-AC12"), ("DR031", "ESC-AC15")]
    assert "test_ESC_AC15_x" in found[1].message and not found[1].blocking and found[0].blocking

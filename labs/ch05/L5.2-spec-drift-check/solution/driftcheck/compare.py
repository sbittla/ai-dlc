"""Drift: the spec, the contract, the code and the tests no longer say the same thing.

Four functions are the lab's TODOs in starter/: compare_versions, compare_fields,
compare_enums and compare_criteria. Each docstring is the specification;
tests/test_compare.py checks each on facts you can verify by hand.

Every comparison is structural: names, types, enum values, IDs and versions.
None of them can see behaviour. A `>=` changed to `>`, or a test that stopped
asserting what its criterion says, leaves every artifact agreeing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .extract import ENUMS, Facts

# code: (blocks the gate?, title)
CHECKS = {
    "DR001": (True, "Versions differ between spec, contract, code and tests"),
    "DR010": (True, "Contract field missing from the code"),
    "DR011": (True, "Code field missing from the contract"),
    "DR012": (True, "Field type differs between contract and code"),
    "DR013": (True, "Contract field has no data rule in the spec"),
    "DR020": (True, "Enum values differ between contract and code"),
    "DR021": (True, "Enum values differ between spec and contract"),
    "DR030": (True, "Spec criterion has no test"),
    "DR031": (False, "Test names a criterion the spec does not have"),
}


@dataclass(frozen=True)
class Drift:
    code: str
    item: str
    message: str

    @property
    def blocking(self) -> bool:
        return CHECKS[self.code][0]


def drift(code: str, item: str, message: str) -> Drift:
    if code not in CHECKS:
        raise KeyError(code)
    return Drift(code, item, message)


# ------------------------------------------------------------------ TODO 1

def compare_versions(facts: Facts) -> list[Drift]:
    """At most one DR001, item "version", when the versions are not all equal.

    The versions are facts.spec_version, facts.contract_version, facts.code_version and
    every value in facts.test_versions; an empty string counts as a version ("missing").
    The message lists each source and its version, as "spec 1.1.0, contract 1.0.0, ...",
    with "missing" for an empty one, in that order and test modules sorted by name.
    """
    sources = [("spec", facts.spec_version), ("contract", facts.contract_version), ("code", facts.code_version)]
    sources += sorted(facts.test_versions.items())
    if len({v for _, v in sources}) <= 1:
        return []
    return [drift("DR001", "version", ", ".join(f"{name} {v or 'missing'}" for name, v in sources))]


# ------------------------------------------------------------------ TODO 2

def compare_fields(facts: Facts) -> list[Drift]:
    """Contract fields against code fields and the spec's data rules. Items are "Def.field".

    - DR010 for each contract field (sorted) not in facts.code_fields.
    - DR011 for each code field (sorted) not in facts.contract_fields.
    - DR012 for each field in both (sorted) whose JSON types differ; the message names both.
    - DR013 for each contract field (sorted) with no entry in facts.data_rules.
    Report all DR010s, then DR011s, then DR012s, then DR013s.
    """
    contract, code = facts.contract_fields, facts.code_fields
    out = [drift("DR010", f, "in the contract, not in the code") for f in sorted(set(contract) - set(code))]
    out += [drift("DR011", f, "in the code, not in the contract") for f in sorted(set(code) - set(contract))]
    out += [drift("DR012", f, f"contract {contract[f]}, code {code[f]}") for f in sorted(set(contract) & set(code))
            if contract[f] != code[f]]
    out += [drift("DR013", f, "no classification in the spec's data rules") for f in sorted(contract)
            if f not in facts.data_rules]
    return out


# ------------------------------------------------------------------ TODO 3

def compare_enums(facts: Facts) -> list[Drift]:
    """Enum values, for each constant in facts.contract_enums (sorted by name). Item: the constant.

    - DR020 if facts.code_constants has no such constant, or its values differ from the
      contract's (as sets). The message lists values only in the contract and only in the code.
    - DR021 if the constant is a key of extract.ENUMS and the spec table that ENUMS names
      (facts.spec_tables[ENUMS[name]], empty if absent) differs from the contract's values (as sets).
    For one constant, report DR020 before DR021.
    """
    out = []
    for name in sorted(facts.contract_enums):
        values = set(facts.contract_enums[name])
        code = set(facts.code_constants.get(name, ()))
        if name not in facts.code_constants or code != values:
            out.append(drift("DR020", name, f"only in contract: {sorted(values - code)}; "
                                            f"only in code: {sorted(code - values)}"))
        if name in ENUMS:
            spec = set(facts.spec_tables.get(ENUMS[name], ()))
            if spec != values:
                out.append(drift("DR021", name, f"only in contract: {sorted(values - spec)}; "
                                                f"only in spec: {sorted(spec - values)}"))
    return out


# ------------------------------------------------------------------ TODO 4

def compare_criteria(facts: Facts) -> list[Drift]:
    """Spec criteria against the IDs test names carry.

    - DR030 for each criterion in facts.criteria (spec order) with no entry in facts.tested.
    - DR031 for each ID in facts.tested (sorted) that is not in facts.criteria; the message
      names the test(s).
    """
    out = [drift("DR030", c, "no test named after it") for c in facts.criteria if c not in facts.tested]
    out += [drift("DR031", c, ", ".join(facts.tested[c])) for c in sorted(facts.tested) if c not in facts.criteria]
    return out


# ------------------------------------------------------------------ provided

def detect(facts: Facts) -> list[Drift]:
    return compare_versions(facts) + compare_fields(facts) + compare_enums(facts) + compare_criteria(facts)

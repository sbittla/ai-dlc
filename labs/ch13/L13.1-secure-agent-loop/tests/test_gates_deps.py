"""Hand-checkable tests for TODO 1 (the gate) and TODO 2 (the dependency gate)."""

from datetime import date

from conftest import DATA_DIR

from secloop import gate_policy, load_json, mirror_policy
from secloop.deps import check_requirements, edit_distance, normalize
from secloop.gates import BLOCKED, CANNOT_CHECK, PASS, decide, suppression_problem
from secloop.sarif import Finding

POLICY = gate_policy()
DAY = date(2027, 1, 28)
ALL = {"semgrep", "gitleaks", "trivy"}


def f(scanner="semgrep", rule="r1", severity=8.0, fp="aaaa"):
    return Finding(scanner, rule, severity, "X1", "src/x.py", 3, fp, "m")


def sup(**kw):
    base = {"id": "S1", "rule": "r1", "fingerprint": "aaaa", "reason": "constant", "author": "coding-session",
            "reviewed_by": "sam.o", "created": "2027-01-20", "expires": "2027-03-01"}
    base.update(kw)
    return base


# ------------------------------------------------------------------ TODO 1

def test_high_sast_blocks_and_medium_warns():
    r = decide([f(severity=7.0), f(severity=6.9, fp="b")], POLICY, [], DAY, "ci", ALL)
    assert r.status == BLOCKED and len(r.blocking) == 1 and len(r.warnings) == 1


def test_any_secret_blocks_whatever_its_severity():
    assert decide([f("gitleaks", severity=1.0)], POLICY, [], DAY, "pre-commit", ALL).status == BLOCKED


def test_trivy_does_not_run_before_commit():
    assert decide([f("trivy", severity=9.0)], POLICY, [], DAY, "pre-commit", ALL).status == PASS
    assert decide([f("trivy", severity=9.0)], POLICY, [], DAY, "ci", ALL).status == BLOCKED


def test_a_missing_report_cannot_be_checked():
    r = decide([], POLICY, [], DAY, "ci", {"semgrep"})
    assert r.status == CANNOT_CHECK and r.missing == ["gitleaks", "trivy"]


def test_a_valid_suppression_silences_one_finding():
    r = decide([f(), f(fp="other")], POLICY, [sup()], DAY, "ci", ALL)
    assert [s for _, s in r.suppressed] == ["S1"] and len(r.blocking) == 1


def test_invalid_suppressions_are_ignored_with_a_reason():
    assert suppression_problem(sup(reviewed_by="coding-session"), POLICY, DAY).startswith("reviewer")
    assert suppression_problem(sup(reviewed_by="priya.n", author="priya.n"), POLICY, DAY) == \
        "reviewed by its own author"
    assert suppression_problem(sup(expires="2027-01-27"), POLICY, DAY) == "expired on 2027-01-27"
    assert suppression_problem(sup(expires="2027-06-01"), POLICY, DAY) == "longer than 90 days"
    assert suppression_problem(sup(reason=" "), POLICY, DAY) == "no reason"
    r = decide([f()], POLICY, [sup(reviewed_by="coding-session")], DAY, "ci", ALL)
    assert r.status == BLOCKED and r.ignored_suppressions[0][0] == "S1"


def test_dependency_findings_cannot_be_suppressed():
    r = decide([f("depgate", rule="DEP001")], POLICY, [sup(rule="DEP001")], DAY, "ci", ALL)
    assert r.status == BLOCKED and "cannot be suppressed" in r.ignored_suppressions[0][1]


# ------------------------------------------------------------------ TODO 2

MIRROR = load_json(DATA_DIR / "packages" / "mirror-index.json")
PUBLIC = load_json(DATA_DIR / "packages" / "public-index.json")
GUNICORN = "gunicorn==23.0.0 --hash=sha256:853e47c194f2dac0fe6d7832e8c60e8b7a00ca9c15fc88fc98ddc36088e13aaf"


def rules(lines):
    return [(x.rule, x.line) for x in check_requirements("X1", "deploy/requirements.txt", lines, mirror_policy(),
                                                         MIRROR, PUBLIC)]


def test_helpers():
    assert normalize("Jwt_OIDC.verify") == "jwt-oidc-verify"
    assert edit_distance("gunicorm", "gunicorn") == 1 and edit_distance("crpytography", "cryptography") == 1


def test_an_admitted_pinned_hashed_package_passes():
    assert rules([GUNICORN]) == []


def test_a_hallucinated_name_is_not_admitted_and_says_so():
    found = check_requirements("X1", "p", ["fastjsonschema-validate==1.2.0"], mirror_policy(), MIRROR, PUBLIC)
    assert [x.rule for x in found] == ["DEP004", "DEP001"]
    assert "not on the public index either" in found[1].message
    attacker = check_requirements("X1", "p", ["jwt-oidc-verify==1.2.0"], mirror_policy(), MIRROR, PUBLIC)
    assert "source distribution only, no source repository" in attacker[1].message


def test_a_typosquat_names_its_target():
    found = check_requirements("X1", "p", ["gunicorm==1.0.0 --hash=sha256:" + "a" * 64], mirror_policy(), MIRROR,
                               PUBLIC)
    assert [x.rule for x in found] == ["DEP001", "DEP002"] and "from gunicorn" in found[1].message


def test_an_unserved_internal_name_is_refused_even_if_nobody_published_it():
    assert rules(["relay-sdk-tools==1.2.0 --hash=sha256:" + "d" * 64]) == [("DEP003", 1)]


def test_dependency_confusion_both_ways():
    assert rules(["--extra-index-url https://pypi.org/simple/", "relay-schemas>=1.4"]) == [("DEP003", 1),
                                                                                           ("DEP004", 2)]
    assert rules(["relay-schemas==99.0.0 --hash=sha256:" + "b" * 64]) == [("DEP003", 1)]
    assert rules(["--index-url https://pypi.org/simple/"]) == [("DEP003", 1)]


def test_a_changed_file_or_unserved_version_is_found():
    assert rules([GUNICORN.replace("853e47", "000000")]) == [("DEP005", 1)]
    assert rules(["gunicorn==24.0.0 --hash=sha256:" + "c" * 64]) == [("DEP005", 1)]


def test_a_vulnerable_but_admitted_version_passes_the_dependency_gate():
    """Known vulnerabilities are Trivy's job; the dependency gate only checks where a file comes from."""
    line = next(f for f in MIRROR["projects"]["pyjwt"]["files"] if f["version"] == "2.3.0")
    assert rules([f"pyjwt==2.3.0 --hash=sha256:{line['sha256']}"]) == []

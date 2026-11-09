"""Hand-checkable tests for TODO 3 (fix re-verification), TODO 4 (catch report) and TODO 5 (release check)."""

import json
import shutil

from conftest import DATA_DIR

from secloop import gate_policy, load_json
from secloop.catch import catch_report, wilson
from secloop.fixes import verify_fix
from secloop.release import check_release

POLICY = gate_policy()


def fix(**kw):
    base = {"change": "X1", "kind": "proper", "claim": "fixed", "files_changed": ["src/x.py"], "added_lines": [],
            "rescan_findings": 0, "tests_pass": True}
    base.update(kw)
    return base


# ------------------------------------------------------------------ TODO 3

def test_a_proper_fix_is_accepted():
    assert verify_fix(fix(), ["src/x.py"], POLICY) == []


def test_each_kind_of_bad_fix_is_refused_with_its_reason():
    assert verify_fix(fix(rescan_findings=2), ["src/x.py"], POLICY) == ["rescan still finds 2"]
    assert verify_fix(fix(tests_pass=False), ["src/x.py"], POLICY) == ["tests fail"]
    assert verify_fix(fix(added_lines=["x = 1  # nosemgrep"]), ["src/x.py"], POLICY) == ["adds marker nosemgrep"]
    assert verify_fix(fix(files_changed=["src/x.py", "tests/test_x.py"]), ["src/x.py"], POLICY) == [
        "changes protected path tests/test_x.py"]
    assert verify_fix(fix(files_changed=["src/y.py"]), ["src/x.py"], POLICY) == [
        "changes a file outside the change: src/y.py"]


def test_reasons_accumulate_in_order():
    bad = fix(rescan_findings=1, tests_pass=False, added_lines=["# gitleaks:allow"],
              files_changed=["security/gitleaks.toml"])
    assert verify_fix(bad, ["src/x.py"], POLICY) == ["rescan still finds 1", "tests fail", "adds marker gitleaks:allow",
                                                     "changes protected path security/gitleaks.toml"]


# ------------------------------------------------------------------ TODO 4

def test_catch_report_by_stage_and_category():
    truth = {"A": {"seeded": True, "category": "sqli"}, "B": {"seeded": True, "category": "sqli"},
             "C": {"seeded": True, "category": "dep"}, "D": {"seeded": False, "category": "clean"},
             "E": {"seeded": False, "category": "clean"}}
    out = {"A": {"pre-commit": 1, "ci": 1, "blocking_scanners": {"semgrep"}},
           "B": {"pre-commit": 0, "ci": 0, "blocking_scanners": set()},
           "C": {"pre-commit": 0, "ci": 1, "blocking_scanners": {"trivy", "depgate"}},
           "D": {"pre-commit": 0, "ci": 1, "blocking_scanners": {"semgrep"}},
           "E": {"pre-commit": 0, "ci": 0, "blocking_scanners": set()}}
    rep = catch_report(out, truth)
    assert [(r.name, r.n, r.pre_commit, r.ci_only, r.escaped) for r in rep.rows] == [("sqli", 2, 1, 0, 1),
                                                                                     ("dep", 1, 0, 1, 0)]
    assert (rep.total.n, rep.total.caught) == (3, 2)
    assert rep.by_scanner == {"depgate": 1, "semgrep": 1, "trivy": 1}
    assert (rep.clean_n, rep.clean_blocked) == (2, 1)


def test_wilson_matches_chapter_7():
    lo, hi = wilson(83, 100)
    assert (round(100 * lo, 1), round(100 * hi, 1)) == (74.5, 89.1)


# ------------------------------------------------------------------ TODO 5

TRUST = load_json(DATA_DIR / "releases" / "trust-root.json")


def test_the_good_candidate_passes():
    assert check_release(DATA_DIR / "releases" / "RC-1", TRUST, "4.25.0") == []


def test_the_wrong_version_fails_identity(tmp_path):
    assert [r for r, _ in check_release(DATA_DIR / "releases" / "RC-1", TRUST, "4.24.0")] == ["REL002"]


def test_a_swapped_artifact_fails_the_subject(tmp_path):
    rc = tmp_path / "rc"
    shutil.copytree(DATA_DIR / "releases" / "RC-1", rc)
    (rc / "artifact.json").write_text(json.dumps({"image": "relay", "digest": "sha256:" + "0" * 64}), encoding="utf-8")
    assert [r for r, _ in check_release(rc, TRUST, "4.25.0")] == ["REL004"]


def test_an_edited_bundle_fails_the_signature(tmp_path):
    rc = tmp_path / "rc"
    shutil.copytree(DATA_DIR / "releases" / "RC-1", rc)
    b = json.loads((rc / "bundle.json").read_text(encoding="utf-8"))
    b["certificate"]["not_after"] = "2027-12-31T00:00:00Z"
    (rc / "bundle.json").write_text(json.dumps(b), encoding="utf-8")
    assert [r for r, _ in check_release(rc, TRUST, "4.25.0")] == ["REL001"]

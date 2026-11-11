"""Version claims and mirror-only updates (4.31.0, ADR-054). The package names are fictional: sessionkeel and
ferncache do not exist on the public index (checked 2026-11-10), and nothing here installs anything."""

import pytest

from relay.maintenance import bump_kind, parse, plan_update
from relay.maintenance.evidence import lock_matches_mirror
from relay.maintenance.updates import Mirror, apply, locked_versions, read_lock, revert

H = {v: (c * 64) for v, c in (("2.4.1", "1"), ("2.4.2", "2"), ("2.5.0", "3"), ("2.5.1", "4"), ("3.0.0", "5"),
                               ("2.4.3", "6"), ("1.8.3", "7"), ("1.8.4", "8"))}
MIRROR = Mirror({"new_release_quarantine_days": 7, "projects": [
    {"name": "sessionkeel", "files": [
        {"version": "2.4.1", "sha256": H["2.4.1"], "released_on": "2027-04-12"},
        {"version": "2.5.0", "sha256": H["2.5.0"], "released_on": "2027-05-06"},
        {"version": "2.4.2", "sha256": H["2.4.2"], "released_on": "2027-06-08", "released_early_by": "aisha.r"},
        {"version": "2.5.1", "sha256": H["2.5.1"], "released_on": "2027-06-08"},
        {"version": "3.0.0", "sha256": H["3.0.0"], "released_on": "2027-07-01"},
        {"version": "2.4.3", "sha256": H["2.4.3"], "released_on": "2027-06-21"}]},
    {"name": "ferncache", "files": [{"version": "1.8.3", "sha256": H["1.8.3"]},
                                    {"version": "1.8.4", "sha256": H["1.8.4"], "released_on": "2027-06-20"}]}]})
LOCK = ("--require-hashes\nsessionkeel==2.4.1 \\\n    --hash=sha256:" + H["2.4.1"] +
        "\nferncache==1.8.3 \\\n    --hash=sha256:" + H["1.8.3"] + "\n")
SENSITIVE = frozenset({"sessionkeel"})


@pytest.mark.parametrize("old,new,kind", [
    ("2.4.1", "2.4.2", "patch"), ("2.4.1", "2.5.0", "minor"), ("2.4.1", "3.0.0", "major"),
    ("0.3.1", "0.4.0", "major"), ("0.3.1", "0.3.2", "minor"), ("2.5.0", "2.4.1", "downgrade"),
    ("2.4.1", "2.4.1", "none"), ("2.4.1", "2.5.0rc1", "prerelease"), ("25.0", "25.1", "minor")])
def test_bump_kind_names_what_a_bump_claims(old, new, kind):
    assert bump_kind(old, new) == kind


@pytest.mark.parametrize("bad", ["2", "v2.4.1", "2.4.1.0", "02.4.1", "", "2.4.1 ; rm"])
def test_unparseable_versions_are_refused_not_guessed(bad):
    with pytest.raises(ValueError):
        parse(bad)


def test_the_lock_reader_finds_every_hashed_entry():
    assert locked_versions(LOCK) == {"sessionkeel": "2.4.1", "ferncache": "1.8.3"}
    assert read_lock(LOCK.replace("\n", "\r\n"))["sessionkeel"] == ("2.4.1", H["2.4.1"])


def test_a_refresh_picks_the_newest_served_minor_and_asks_security_for_a_sensitive_package():
    # 9 May: 2.5.0 (6 May) is still in quarantine; 16 May it is served.
    assert plan_update("sessionkeel", LOCK, MIRROR, "2027-05-09", SENSITIVE).refusal == "in_quarantine"
    plan = plan_update("sessionkeel", LOCK, MIRROR, "2027-05-16", SENSITIVE)
    assert (plan.target, plan.bump, plan.refusal) == ("2.5.0", "minor", None)
    assert "security" in plan.reviews and "pinned-defaults" in plan.reviews


def test_a_fix_is_the_smallest_served_change_on_the_same_minor_line():
    plan = plan_update("sessionkeel", LOCK, MIRROR, "2027-06-09", SENSITIVE, fixed="2.4.2",
                       advisory="LAB-ADV-2027-0113")
    assert (plan.target, plan.bump) == ("2.4.2", "patch")   # released early by aisha.r; 2.5.1 is a feature line
    assert plan.reviews == ("pinned-defaults", "tests", "scan", "security")


def test_a_major_bump_is_never_proposed_and_a_missing_package_is_not_invented():
    lock = LOCK.replace("2.4.1", "2.9.9")
    m = Mirror({"projects": [{"name": "sessionkeel", "files": [{"version": "3.0.0", "sha256": H["3.0.0"]}]}]})
    assert plan_update("sessionkeel", lock.replace(H["2.4.1"], H["2.4.1"]), m, "2027-06-09", SENSITIVE).refusal \
        == "major_needs_a_person"
    assert plan_update("tallowcsv", LOCK, MIRROR, "2027-06-09", SENSITIVE).refusal == "not_locked"


def test_a_patch_of_an_ordinary_package_needs_no_security_review():
    plan = plan_update("ferncache", LOCK, MIRROR, "2027-06-28", SENSITIVE)
    assert (plan.target, plan.bump) == ("1.8.4", "patch") and "security" not in plan.reviews


def test_apply_and_revert_change_one_entry_and_keep_the_mirror_hash():
    plan = plan_update("sessionkeel", LOCK, MIRROR, "2027-06-09", SENSITIVE, fixed="2.4.2")
    new = apply(LOCK, plan, MIRROR)
    assert locked_versions(new) == {"sessionkeel": "2.4.2", "ferncache": "1.8.3"}
    assert lock_matches_mirror(new, MIRROR).result == "pass"
    assert revert(new, plan, MIRROR) == LOCK
    with pytest.raises(ValueError):
        revert(LOCK, plan, MIRROR)


def test_a_lock_whose_hash_is_not_the_mirrors_fails_the_check():
    bad = LOCK.replace(H["1.8.3"], "f" * 64)
    assert lock_matches_mirror(bad, MIRROR).result == "fail"

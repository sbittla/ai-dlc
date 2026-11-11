"""Evidence gathered in the sandbox (4.31.0, ADR-054): a reproduction must fail before and pass after, pinned
defaults catch a changed default, and a refusal is never a pass. These start real processes (Chapter 18's
sandbox). The module under test is a small inert stand-in for a fictional session library."""

from relay.maintenance import Bundle, Check, item, reproduce, sandbox_check
from relay.maintenance.evidence import defaults_script

LIB = '''
def verify(claims, now, audience=None, require_audience={req}):
    exp = claims.get("exp")
    if {strict} and not isinstance(exp, (int, float)):
        return False
    if isinstance(exp, (int, float)) and now > exp:
        return False
    if require_audience and claims.get("aud") != audience:
        return False
    return True
'''
OLD = {"keel.py": LIB.format(req=False, strict=False)}       # the vulnerable release
FIXED = {"keel.py": LIB.format(req=False, strict=True)}      # the fix, same defaults
CHANGED = {"keel.py": LIB.format(req=True, strict=True)}     # a "minor" release that changed a default
REPRO = ("import sys, keel\n"
         "ok = keel.verify({'exp': '100', 'sub': 'u1'}, now=200)\n"
         "print('expired token accepted' if ok else 'expired token refused')\n"
         "sys.exit(1 if ok else 0)\n")
PINNED = {"verify": {"audience": None, "require_audience": False}}


def test_a_confirmed_fix_fails_before_and_passes_after():
    r = reproduce(OLD, FIXED, REPRO)
    assert (r.outcome, r.before.result, r.after.result) == ("fixed", "fail", "pass")
    assert r.before.detail == "expired token accepted"


def test_a_report_that_does_not_reproduce_is_not_fixed_by_the_bot():
    assert reproduce(FIXED, FIXED, REPRO).outcome == "not_reproduced"
    assert reproduce(OLD, OLD, REPRO).outcome == "not_fixed"


def test_pinned_defaults_pass_on_the_fix_and_fail_on_a_changed_default():
    script = defaults_script("keel", PINNED)
    assert sandbox_check("defaults", FIXED, script).result == "pass"
    changed = sandbox_check("defaults", CHANGED, script)
    assert changed.result == "fail" and changed.detail == "verify(require_audience): pinned False, now True"


def test_a_reproduction_that_reaches_outside_is_refused_not_passed():
    reporter_poc = "import os, sys\nprint(len(os.environ))\nopen('../outside.txt', 'w').write('x')\nsys.exit(0)\n"
    r = reproduce(OLD, FIXED, reporter_poc)
    assert r.outcome == "refused" and r.before.result == "refused" and r.before.refusals


def test_a_bundle_blocks_on_missing_or_failing_required_evidence_and_hashes_its_labels():
    a = Bundle((item("E1", "tests pass", Check("t", "pass", "")),
                item("E2", "scanner report", Check("s", "pass", ""), status="modelled")))
    b = Bundle((item("E1", "tests pass", Check("t", "pass", "")),
                item("E2", "scanner report", Check("s", "pass", ""), status="verified")))
    assert a.blocking() == [] and a.sha256() != b.sha256()   # relabelling evidence changes what was approved
    c = Bundle(a.items + (item("E3", "guard metric", None, source="deploy"),
                          item("E4", "optional note", Check("n", "fail", ""), required=False)))
    assert c.blocking() == ["E3"]
    assert c.table()[2].startswith("| E1 | tests pass | verified | pass |")

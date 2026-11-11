"""Copies stay in sync with what they copy.

- vendor/adoption/ is Lab 20.1's reference checks, unchanged.
- Every lab-report snapshot in the Relay sample pack is what that lab's reference solution prints today.
- The coverage report is what Lab 15.1 computes today for 4.29.0's code of 30 April 2027.
- The kit's coverage rule agrees with Lab 12.1's own implementation on Lab 12.1's own matrix.

Each test is skipped when the other lab is not present (for example, when the kit is copied out of the repo).
"""

import importlib.util
import json

import pytest

from conftest import DATA_DIR, LAB_ROOT, REPO

from capstone import coverage as cov

LABS = REPO / "labs"
PACK = DATA_DIR / "packs" / "relay-b-4.31.0"


def _gen():
    spec = importlib.util.spec_from_file_location("ch21_gen", LAB_ROOT / "scripts" / "generate_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _need(path):
    if not path.exists():
        pytest.skip(f"{path} is not present")


@pytest.mark.parametrize("name", ["__init__.py", "maturity.py", "tom.py", "roi.py"])
def test_vendored_lab_20_1_checks_are_unchanged(name):
    src = LABS / "ch20" / "L20.1-maturity-operating-model-roi" / "solution" / "adoption" / name
    _need(src)
    norm = lambda p: p.read_bytes().replace(b"\r\n", b"\n")  # noqa: E731
    assert norm(LAB_ROOT / "vendor" / "adoption" / name) == norm(src)


@pytest.mark.parametrize("name", sorted(["lab-12.1-classes.md", "lab-10.1-compare.md", "lab-10.2-drills.md",
                                         "lab-18.1-drills.md", "lab-18.1-trace.md", "lab-17.2-agents.md"]))
def test_lab_report_snapshots_are_current(name):
    gen = _gen()
    lab, argv = gen.SNAPSHOTS[name]
    _need(LABS / lab)
    assert gen.run_lab(LABS / lab, argv) == (PACK / "items" / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["lab-20.1-catalog.md", "lab-20.2-power.md"])
def test_track_c_snapshots_are_current(name):
    gen = _gen()
    lab, argv = gen.C_SNAPSHOTS[name]
    _need(LABS / lab)
    assert gen.run_lab(LABS / lab, argv) == (DATA_DIR / "fixtures" / "c-pass" / "items" / name).read_text(
        encoding="utf-8")


def test_coverage_snapshot_is_what_lab_15_1_computes():
    gen = _gen()
    _need(LABS / "ch15" / "L15.1-hardened-pipeline")
    live = json.loads(gen.run_lab(LABS / "ch15/L15.1-hardened-pipeline", ["-c", gen.L15_EXPORT]))
    assert live == json.loads((PACK / "items" / "coverage-4.29.0.json").read_text(encoding="utf-8"))


L12_EXPORT = """
import json
from redteam.matrix import coverage, gate, load, verify
m = verify('4.26.0')
policy = load('gate-policy.json')
classes = [{'id': c['id'], 'harm': c['harm'], 'cells': [{'control': x.control, 'status': x.status,
           'benign_ok': x.benign_ok} for x in m.row(c['id'])]} for c in m.classes]
controls = {k: {'depends_on': v['depends_on']} for k, v in m.controls.items()}
passed, reasons = gate(m, policy)
print(json.dumps({'classes': classes, 'controls': controls, 'policy': policy, 'coverage': coverage(m),
                  'passed': passed, 'reasons': reasons}))
"""


def test_the_kits_coverage_rule_agrees_with_lab_12_1():
    lab = LABS / "ch12" / "L12.1-agentic-red-team"
    _need(lab)
    out = json.loads(_gen().run_lab(lab, ["-c", L12_EXPORT]))
    assert cov.coverage(out["classes"], out["controls"]) == out["coverage"]
    report = {"policy": out["policy"], "classes": out["classes"], "controls": out["controls"]}
    assert cov.gate(report) == (out["passed"], out["reasons"])
    assert out["passed"] is False      # 4.26.0 fails on C10, C11 and C14 (Chapter 12)


def test_relay_sources_are_canonical_4_31_0():
    relay = REPO / "labs" / "relay-baselines" / "4.31.0" / "relay-repo"
    _need(relay)
    from capstone import evidence
    res = evidence.check(PACK)
    assert not [f for f in res.findings if f.code in ("EV002", "EV003", "EV005")]

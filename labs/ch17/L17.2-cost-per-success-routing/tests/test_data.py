"""The data reproduces, its copies match their sources, and the copied simulator reproduces Chapter 7's numbers."""

import json
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT

LABS = LAB_ROOT.parent.parent
L171 = LAB_ROOT.parent / "L17.1-load-test-bottleneck" / "relay-repo" / "src" / "relay"
L101 = LABS / "ch10" / "L10.1-workflow-agent-multiagent" / "solution"
GENERATED = {"abuse.json", "configs.json", "incident.json", "models.json", "source/tickets.jsonl",
             "source/tickets-per-minute.csv", "relay-4.28.0/src/relay/__init__.py",
             "relay-4.28.0/src/relay/routing/__init__.py", "relay-4.28.0/src/relay/routing/costs.py",
             "relay-4.28.0/src/relay/routing/policy.py", "relay-4.28.0/src/relay/routing/quota.py"}


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == GENERATED
    for rel in GENERATED:
        assert (tmp_path / rel).read_bytes() == (DATA_DIR / rel).read_bytes(), rel
    assert files(DATA_DIR) - GENERATED == {"source/ch10-runs.jsonl"}


def test_configured_files_say_so():
    for name in ("abuse.json", "configs.json", "incident.json", "models.json"):
        assert "CONFIGURED" in json.loads((DATA_DIR / name).read_text(encoding="utf-8"))["GENERATED"]


def test_the_vendored_routing_package_is_lab_17_1s():
    if not L171.is_dir():
        return
    for p in sorted((L171 / "routing").glob("*.py")):
        ours = DATA_DIR / "relay-4.28.0" / "src" / "relay" / "routing" / p.name
        assert ours.read_bytes() == p.read_bytes().replace(b"\r\n", b"\n"), p.name


def test_the_copied_simulator_reproduces_chapter_7():
    from costlab.compare import offline
    a = offline("large")
    assert round(a.accuracy, 3) == 0.860 and round(a.usd_per_correct, 6) == 0.002510  # Table 7.7, triage-v3.1


def test_the_ch10_extraction_reproduces_and_matches_chapter_10(tmp_path):
    from costlab.agentcost import design_costs
    routed = next(d for d in design_costs() if d.design == "routed")
    assert (round(routed.per_run, 3), round(routed.per_success, 3)) == (0.168, 0.231)  # Table 10.10
    if not L101.is_dir():
        return
    out = tmp_path / "ch10-runs.jsonl"
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "extract_ch10.py"), "--out", str(out)], check=True,
                   capture_output=True, timeout=600)
    assert out.read_bytes() == (DATA_DIR / "source" / "ch10-runs.jsonl").read_bytes()

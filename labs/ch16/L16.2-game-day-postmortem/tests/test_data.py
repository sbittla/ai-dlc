"""The data is reproducible and labelled; the vendored Relay is Lab 16.1's 4.27.0, unchanged."""

import json
import subprocess
import sys
from pathlib import Path

from conftest import DATA_DIR, LAB_ROOT, VENDOR

L161 = LAB_ROOT.parent / "L16.1-otel-redaction-slo" / "relay-repo"


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_every_file_is_labelled_generated_and_the_assistant_simulated():
    for path in sorted(DATA_DIR.rglob("*")):
        if path.suffix == ".json":
            assert "GENERATED" in json.loads(path.read_text(encoding="utf-8"))["label"], path.name
        elif path.suffix in (".csv", ".md"):
            assert "GENERATED" in path.read_text(encoding="utf-8").splitlines()[0], path.name
    # trail.jsonl holds audit-trail records exactly as relay.audit writes them; plan.json labels the scenario.
    for name in ("assistant-v0.json", "assistant-v1.json"):
        assert "SIMULATED" in json.loads((DATA_DIR / "incident-2027-02-02" / name).read_text())["label"]


def norm(p: Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def test_vendored_relay_is_lab_16_1s_copy():
    if not L161.is_dir():
        return
    for pkg in ("telemetry", "audit"):
        ours = sorted(p.name for p in (VENDOR / "relay" / pkg).glob("*.py"))
        theirs = sorted(p.name for p in (L161 / "src" / "relay" / pkg).glob("*.py"))
        assert ours == theirs
        for name in ours:
            assert norm(VENDOR / "relay" / pkg / name) == norm(L161 / "src" / "relay" / pkg / name), name
    for rel in ("infra/detection/rules.json", "infra/detection/service-rules.json", "infra/monitoring/routing.json",
                "infra/monitoring/alerts.json", "docs/slo/slos.json"):
        assert norm(VENDOR / "config" / Path(rel).name) == norm(L161 / rel), rel


def test_data_files_are_ascii():
    for path in DATA_DIR.rglob("*"):
        if path.is_file():
            path.read_bytes().decode("ascii")

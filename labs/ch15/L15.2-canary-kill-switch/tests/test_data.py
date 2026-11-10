"""The scenarios reproduce byte for byte, and vendor/ is Lab 15.1's Relay 4.29.0, unchanged."""

import json
import subprocess
import sys

from conftest import DATA_DIR, L151_RELAY, LAB_ROOT, VENDOR


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == files(DATA_DIR)
    for rel in files(DATA_DIR):
        assert (tmp_path / rel).read_bytes() == (DATA_DIR / rel).read_bytes(), rel


def test_every_scenario_is_labelled_generated():
    for rel in files(DATA_DIR):
        assert "GENERATED" in (DATA_DIR / rel).read_text(encoding="utf-8"), rel
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["traffic"] == ["R1", "R2", "R3", "R4", "R5", "R6"] and manifest["ai"] == ["A1", "A0"]


def test_vendor_is_lab_15_1s_relay():
    if not L151_RELAY.is_dir():
        return
    pairs = {"relay/__init__.py": "src/relay/__init__.py", "relay/release/__init__.py": "src/relay/release/__init__.py",
             "relay/release/flags.py": "src/relay/release/flags.py", "relay/release/judged.py":
             "src/relay/release/judged.py", "config/canary.json": "deploy/rollout/canary.json",
             "config/flags.json": "deploy/flags.json", "config/slos.json": "docs/slo/slos.json"}
    assert files(VENDOR) == set(pairs)
    for ours, theirs in pairs.items():
        a = (VENDOR / ours).read_bytes().replace(b"\r\n", b"\n")
        b = (L151_RELAY / theirs).read_bytes().replace(b"\r\n", b"\n")
        assert a == b, ours

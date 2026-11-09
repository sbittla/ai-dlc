"""The data is reproducible, labelled as generated, and holds no real secret."""

import json
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_every_file_says_it_was_generated():
    for path in sorted(DATA_DIR.rglob("*.json")):
        assert "GENERATED" in json.loads(path.read_text(encoding="utf-8"))["label"], path.name
    for path in sorted(DATA_DIR.rglob("*.csv")):
        assert path.read_text(encoding="utf-8").startswith("# GENERATED"), path.name


def test_the_traffic_covers_30_days_by_the_minute():
    lines = (DATA_DIR / "traffic" / "api-minutes.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 + 30 * 1440
    assert lines[2].startswith("2027-01-04T00:00Z") and lines[-1].startswith("2027-02-02T23:59Z")


def test_the_only_token_shaped_string_is_the_labelled_fake():
    pattern = re.compile(r"rly_(live|test)_[0-9a-f]{32}")
    found = set()
    for path in DATA_DIR.rglob("*"):
        if path.is_file():
            found |= {m.group(0) for m in pattern.finditer(path.read_text(encoding="utf-8"))}
    assert found <= {"rly_live_" + "f0e1d2c3b4a59687" * 2}
    assert "FAKE" in (LAB_ROOT / "scripts" / "generate_data.py").read_text(encoding="utf-8")


def test_data_files_are_ascii():
    for path in DATA_DIR.rglob("*"):
        if path.is_file():
            path.read_bytes().decode("ascii")

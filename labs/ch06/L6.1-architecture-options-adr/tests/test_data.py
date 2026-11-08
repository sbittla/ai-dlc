"""The generator reproduces data/ byte for byte."""

import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    script = (LAB_ROOT / "scripts" / "generate_data.py").read_text(encoding="utf-8")
    copy = tmp_path / "scripts" / "generate_data.py"
    copy.parent.mkdir()
    copy.write_text(script, encoding="utf-8")
    subprocess.run([sys.executable, str(copy)], check=True, capture_output=True)
    out = tmp_path / "data"
    after = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert after == before

"""The generator reproduces rules.json and the seeded cases byte for byte."""

import shutil
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and not p.relative_to(root).as_posix().startswith("relay-repo/")}


def test_generator_reproduces_committed_data(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy(LAB_ROOT / "scripts" / "generate_data.py", tmp_path / "scripts" / "generate_data.py")
    shutil.copytree(DATA_DIR / "relay-repo", tmp_path / "data" / "relay-repo")
    subprocess.run([sys.executable, str(tmp_path / "scripts" / "generate_data.py")], check=True, capture_output=True)
    assert snapshot(tmp_path / "data") == snapshot(DATA_DIR)

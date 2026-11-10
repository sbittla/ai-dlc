"""The generated data reproduces byte for byte; the model manifest admits only safe files at a pinned revision;
the optional real-run script compiles and is never imported by the lab's own code."""

import json
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT

GENERATED = {"manifest.json", "serving.json", "workload.json", "relay-volume.json", "model-manifest.json"}


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == GENERATED
    for rel in GENERATED:
        assert (tmp_path / rel).read_bytes() == (DATA_DIR / rel).read_bytes().replace(b"\r\n", b"\n"), rel


def test_the_manifest_pins_a_revision_and_admits_only_safetensors_and_json():
    m = json.loads((DATA_DIR / "model-manifest.json").read_text(encoding="utf-8"))
    assert len(m["revision"]) == 40 and m["file_format"] == "safetensors"
    assert all(name.endswith((".json", ".safetensors")) for name in m["files"])
    assert all(len(f["sha256"]) == 64 for f in m["files"].values())
    assert "*.bin" in m["never_download"] and "*.pkl" in m["never_download"]
    total = sum(f["bytes"] for f in m["files"].values())
    assert round(total / 1_000_000) == 271  # the download size the README states


def test_the_recorded_run_matches_the_manifest():
    run = json.loads((DATA_DIR / "measured" / "smollm2-135m-author.json").read_text(encoding="utf-8"))
    m = json.loads((DATA_DIR / "model-manifest.json").read_text(encoding="utf-8"))
    assert (run["model"], run["revision"], run["verified_sha256"]) == (m["model"], m["revision"], True)


def test_the_real_run_script_compiles_and_the_lab_never_imports_it():
    source = (LAB_ROOT / "scripts" / "run_real_model.py").read_text(encoding="utf-8")
    compile(source, "run_real_model.py", "exec")
    assert "use_safetensors=True" in source and "allow_patterns" in source
    import ast
    for folder in ("starter", "solution"):
        for path in (LAB_ROOT / folder / "servelab").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
            names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
            assert not [m for m in names if m.split(".")[0] in ("torch", "transformers", "huggingface_hub")], path

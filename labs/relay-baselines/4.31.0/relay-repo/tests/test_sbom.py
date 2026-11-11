"""The SBOM and AI-BOM (4.25.0, ADR-030): complete against the lock file, the images and the AI components,
deterministic, and refusing a model file that can run code when it is loaded."""

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sbom  # noqa: E402

DIGEST = "sha256:8d0eeba9d26884f38d5e97f75f1314f80ab8e7b6b7999544d4b484ecbe300b0c"


def test_every_locked_package_is_in_the_sbom_with_its_hash_and_source():
    bom = sbom.build_sbom(ROOT, "4.25.0", DIGEST, "2027-01-28")
    libs = {c["purl"]: c for c in bom["components"] if c["type"] == "library"}
    assert set(libs) == {"pkg:pypi/gunicorn@23.0.0", "pkg:pypi/packaging@25.0"}
    assert libs["pkg:pypi/gunicorn@23.0.0"]["hashes"][0]["content"].startswith("853e47c1")
    assert all({"name": "relay:source", "value": "https://pypi-mirror.relay.example/simple/"} in c["properties"]
               for c in libs.values())


def test_the_sbom_names_the_image_digest_and_the_base_image_digest():
    bom = sbom.build_sbom(ROOT, "4.25.0", DIGEST, "2027-01-28")
    assert bom["specVersion"] == "1.6" and bom["metadata"]["component"]["hashes"][0]["content"] == DIGEST[7:]
    base = next(c for c in bom["components"] if c["bom-ref"] == "base-image")
    assert base["purl"].startswith("pkg:oci/python@sha256%3Ab156cf60")


def test_the_ai_bom_lists_models_prompts_datasets_gates_tools_and_every_agent():
    bom = sbom.build_aibom(ROOT, "4.25.0", DIGEST, "2027-01-28")
    kinds = {}
    for item in bom["components"] + bom["services"]:
        kind = next(p["value"] for p in item["properties"] if p["name"] == "relay:kind")
        kinds.setdefault(kind, []).append(item["name"])
    assert kinds == {"model": ["triage-model", "sim-large"], "prompt": ["triage-v3.1"],
                     "dataset": ["relay-triage-eval"], "evaluation-gate": ["triage-gate-v1"],
                     "tool-server": ["relay-db-readonly"],
                     "agent": ["analytics-sync", "ci-failure-triage", "coding-session", "dataset-refresh",
                               "eval-harvester", "maintenance-bot", "spec-to-pr-helper", "triage-worker"]}


def test_the_output_is_deterministic(tmp_path):
    for out in ("a", "b"):
        assert sbom.main(["--image-digest", DIGEST, "--date", "2027-01-28", "--out-dir", str(tmp_path / out)]) == 0
    for name in ("sbom.cdx.json", "aibom.cdx.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_a_pickled_model_file_is_refused(tmp_path):
    root = tmp_path / "repo"
    for rel in ("supply-chain", "governance", "deploy"):
        shutil.copytree(ROOT / rel, root / rel)
    shutil.copy(ROOT / "pyproject.toml", root / "pyproject.toml")
    path = root / "supply-chain" / "ai-components.json"
    ai = json.loads(path.read_text(encoding="utf-8"))
    ai["models"].append(dict(ai["models"][1], name="router", file_format="pickle"))
    path.write_text(json.dumps(ai), encoding="utf-8")
    with pytest.raises(ValueError, match="pickle"):
        sbom.build_aibom(root, "4.25.0", DIGEST, "2027-01-28")


def test_a_bad_digest_is_refused():
    with pytest.raises(SystemExit):
        sbom.main(["--image-digest", "latest", "--date", "2027-01-28"])

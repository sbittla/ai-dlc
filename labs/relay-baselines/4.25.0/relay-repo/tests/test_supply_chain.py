"""Supply-chain fitness checks (4.25.0, ADR-028): tools/supplychain.py finds nothing in the repository, and finds
each kind of problem in a copy that has it. The copies are made in a temporary folder; nothing reaches a registry."""

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import supplychain  # noqa: E402

GOOD_PIN = ("gunicorn==23.0.0 \\\n    --hash=sha256:853e47c194f2dac0fe6d7832e8c60e8b7a00ca9c15fc88fc98ddc36088e13aaf")


def copy(tmp_path) -> Path:
    dest = tmp_path / "repo"
    for rel in ("supply-chain", "deploy", ".devcontainer", ".github", "infra", "governance"):
        shutil.copytree(ROOT / rel, dest / rel)
    for rel in ("pyproject.toml", "requirements-dev.txt", ".mcp.json"):
        shutil.copy(ROOT / rel, dest / rel)
    return dest


def rules(root: Path) -> list[str]:
    return sorted(f.rule for f in supplychain.check(root))


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_the_repository_has_no_supply_chain_finding():
    assert supplychain.check(ROOT) == []


def test_the_command_exits_0(capsys):
    assert supplychain.main([]) == 0
    assert "supply-chain: 0 finding(s)" in capsys.readouterr().out


def test_pep_503_normalization():
    assert supplychain.normalize("PyJWT") == supplychain.normalize("pyjwt") == "pyjwt"
    assert supplychain.normalize("jwt_oidc.verify") == "jwt-oidc-verify"


@pytest.mark.parametrize("old, new, expected", [
    (GOOD_PIN, "gunicorn==23.0.0", ["SC001"]),
    (GOOD_PIN, GOOD_PIN.replace("853e47", "000000"), ["SC004"]),
    (GOOD_PIN, GOOD_PIN.replace("23.0.0", "22.0.0"), ["SC004"]),
    (GOOD_PIN, "jwt-oidc-verify==1.2.0 \\\n    --hash=sha256:" + "ab" * 32, ["SC004"]),
    ("--only-binary :all:\n", "", ["SC003"]),
    ("--require-hashes\n", "", ["SC003"]),
    ("--index-url https://pypi-mirror.relay.example/simple/\n",
     "--index-url https://pypi-mirror.relay.example/simple/\n--extra-index-url https://pypi.org/simple/\n", ["SC002"]),
    ("--index-url https://pypi-mirror.relay.example/simple/", "--index-url https://pypi.org/simple/", ["SC002"]),
])
def test_lock_file_problems_are_found(tmp_path, old, new, expected):
    root = copy(tmp_path)
    edit(root / "deploy" / "requirements.txt", old, new)
    assert rules(root) == expected


def test_a_runtime_dependency_is_found(tmp_path):
    root = copy(tmp_path)
    edit(root / "pyproject.toml", "dependencies = []", 'dependencies = ["pyjwt==2.10.1"]')
    assert rules(root) == ["SC005"]


def test_an_image_by_tag_is_found_everywhere_it_can_appear(tmp_path):
    root = copy(tmp_path)
    cf = root / "deploy" / "Containerfile"
    text = cf.read_text(encoding="utf-8")
    cf.write_text(text.replace(text[text.index("FROM "):text.index("\n", text.index("FROM "))],
                               "FROM python:3.12-slim"), encoding="utf-8")
    edit(root / "infra" / "compute.tf", "@${var.image_digest}", ":${var.image_tag}")
    dc = root / ".devcontainer" / "devcontainer.json"
    cfg = json.loads(dc.read_text(encoding="utf-8"))
    cfg["image"] = "mcr.microsoft.com/devcontainers/python:3.12"
    dc.write_text(json.dumps(cfg), encoding="utf-8")
    assert rules(root) == ["SC006", "SC006", "SC006"]


def test_a_digest_that_was_not_reviewed_is_found(tmp_path):
    root = copy(tmp_path)
    edit(root / "deploy" / "egress-proxy" / "Containerfile", "@sha256:42a5", "@sha256:0000")
    assert rules(root) == ["SC006"]


def test_an_action_pinned_by_tag_is_found(tmp_path):
    root = copy(tmp_path)
    edit(root / ".github" / "workflows" / "ci.yml",
         "actions/checkout@1111111111111111111111111111111111111111  # v4, stand-in SHA\n"
         "        with: {persist-credentials: false}\n      - uses: actions/setup-python",
         "actions/checkout@v4\n        with: {persist-credentials: false}\n      - uses: actions/setup-python")
    assert rules(root) == ["SC007"] * 3  # the tests, supply-chain and secret-scan jobs


def test_a_pip_install_without_the_lock_is_found(tmp_path):
    root = copy(tmp_path)
    edit(root / ".github" / "workflows" / "ci.yml",
         "python -m pip install --require-hashes --only-binary :all: -r requirements-dev.txt",
         "python -m pip install pytest==9.1.1")
    assert rules(root) == ["SC009"]


def test_an_mcp_server_that_differs_from_the_reviewed_one_is_found(tmp_path):
    root = copy(tmp_path)
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    mcp["mcpServers"]["relay-db-readonly"]["args"].append("--allow-writes")
    mcp["mcpServers"]["helpful-tools"] = {"command": "npx", "args": ["-y", "helpful-tools@latest"]}
    (root / ".mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    assert rules(root) == ["SC008", "SC008"]


def test_the_proxy_no_longer_reaches_the_public_index():
    allow = (ROOT / "deploy" / "egress-proxy" / "allowlist.txt").read_text(encoding="utf-8")
    entries = [ln for ln in allow.splitlines() if ln and not ln.startswith("#")]
    assert "pypi.org" not in entries and "files.pythonhosted.org" not in entries


def test_the_dev_container_waiver_is_closed():
    waivers = json.loads((ROOT / "governance" / "waivers.json").read_text(encoding="utf-8"))
    assert waivers == {"waivers": []}
    image = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8"))["image"]
    assert "@sha256:" in image


def test_required_checks_include_the_supply_chain_and_security_gates():
    bp = json.loads((ROOT / "governance" / "branch-protection.json").read_text(encoding="utf-8"))
    assert {"tests", "secret-scan", "supply-chain", "security-gates"} <= set(bp["required_status_checks"]["contexts"])


def test_pip_defaults_are_required_in_the_dev_container_and_the_sandbox(tmp_path):
    root = copy(tmp_path)
    dc = root / ".devcontainer" / "devcontainer.json"
    cfg = json.loads(dc.read_text(encoding="utf-8"))
    del cfg["containerEnv"]["PIP_ONLY_BINARY"]
    dc.write_text(json.dumps(cfg), encoding="utf-8")
    edit(root / "infra" / "compute.tf", '{ name = "PIP_REQUIRE_HASHES", value = "1" },', "")
    assert rules(root) == ["SC010", "SC010"]


def test_sc008_checks_the_record_not_the_code(tmp_path):
    """A documented limit: the check compares the launch command with a reviewed record; it does not hash
    relaymcp's code, which is resolved from the import path when the server starts."""
    root = copy(tmp_path)
    ai = json.loads((root / "supply-chain" / "ai-components.json").read_text(encoding="utf-8"))
    ai["tool_servers"][0]["sha256"] = "not-a-hash"
    (root / "supply-chain" / "ai-components.json").write_text(json.dumps(ai), encoding="utf-8")
    assert rules(root) == ["SC008"]

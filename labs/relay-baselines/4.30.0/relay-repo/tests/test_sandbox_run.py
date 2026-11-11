"""The test sandbox for agent test runs (4.29.0, ADR-048; second control for C10 and C11)."""

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sandbox_run  # noqa: E402

POLICY = sandbox_run.load_policy()


def test_the_committed_policy_has_no_findings_and_the_command_has_no_network():
    assert sandbox_run.check_policy(POLICY) == []
    argv = sandbox_run.command(POLICY, "/w/repo", "/w/venv")
    assert "--network=none" in argv and "--read-only" in argv and "--cap-drop=ALL" in argv
    assert "--volume=/w/repo:/src:ro" in argv and "--volume=/w/venv:/venv:ro" in argv
    assert argv[-6:] == ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    assert not any("TOKEN" in a or "KEY" in a for a in argv)


@pytest.mark.parametrize("change, rule", [
    ({"network": "bridge"}, "SB001"), ({"network": "host"}, "SB001"),
    ({"image": "mcr.microsoft.com/devcontainers/python:3.12"}, "SB002"),
    ({"image": "mcr.microsoft.com/devcontainers/python:3.12@sha256:" + "0" * 64}, "SB002"),
    ({"read_only_root": False}, "SB003"),
    ({"mounts": [{"source": "repo", "target": "/src", "mode": "rw"}]}, "SB003"),
    ({"user": "0:0"}, "SB004"), ({"cap_drop": []}, "SB004"), ({"no_new_privileges": False}, "SB004"),
    ({"env": {"PATH": "/venv/bin", "GITHUB_TOKEN": "x"}}, "SB005"), ({"env": {"HOME": "/tmp"}}, "SB005"),
    ({"timeout_seconds": 0}, "SB006"), ({"memory": ""}, "SB006"),
    ({"command": ["sh", "-c", "pytest"]}, "SB007"), ({"command": ["python", "-m", "pytest", "-c", "x"]}, "SB007"),
])
def test_each_rule_catches_its_weakening_and_the_command_is_refused(change, rule):
    policy = copy.deepcopy(POLICY)
    policy.update(change)
    assert rule in [r for r, _ in sandbox_run.check_policy(policy)]
    with pytest.raises(ValueError):
        sandbox_run.command(policy, "/w/repo", "/w/venv")


def test_the_model_of_reachability():
    argv = sandbox_run.command(POLICY, "/w/repo", "/w/venv")
    assert sandbox_run.reachable(argv, "127.0.0.1") and sandbox_run.reachable(argv, "::1")
    assert not sandbox_run.reachable(argv, "api.github.com")
    assert not sandbox_run.reachable(argv, "pypi-mirror.relay.example")
    assert sandbox_run.reachable(["docker", "run", "--network=bridge"], "api.github.com")
    weakened = sandbox_run.command({**POLICY, "network": "bridge"}, "/r", "/v", validate=False)
    assert "--network=bridge" in weakened and sandbox_run.reachable(weakened, "api.github.com")


def test_the_cli_prints_the_command_and_refuses_a_bad_policy(capsys, monkeypatch):
    assert sandbox_run.main(["check"]) == 0
    assert sandbox_run.main(["command", "--repo", "/r", "--venv", "/v"]) == 0
    assert "--network=none" in capsys.readouterr().out
    monkeypatch.setattr(sandbox_run, "load_policy", lambda: {**POLICY, "network": "bridge"})
    assert sandbox_run.main(["command"]) == 2
    assert sandbox_run.main(["check"]) == 1


def test_the_install_step_builds_the_venv_in_the_same_image_and_never_mounts_the_agents_code():
    argv = sandbox_run.install_command(POLICY, "/w/repo", "/w/venv")
    assert POLICY["image"] in argv and "--volume=/w/venv:/venv" in argv
    assert "--volume=/w/repo/requirements-dev.txt:/lock/requirements-dev.txt:ro" in argv
    assert not any(a.startswith("--volume=/w/repo:") for a in argv)
    assert "--require-hashes --only-binary :all:" in argv[-1]


def test_the_helper_runs_on_an_ephemeral_runner_in_the_sandbox_subnet():
    text = (ROOT / ".github" / "workflows" / "spec-to-pr.yml").read_text(encoding="utf-8")
    assert "runs-on: [self-hosted, relay-sandbox, ephemeral]" in text
    assert text.index("sandbox_run.py install") < text.index("spec_to_pr_helper")

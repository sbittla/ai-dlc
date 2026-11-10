"""Run an agent's test run in a container with no network (4.29.0; ADR-048).

Chapter 12 left classes C10 and C11 (data out through an agent's network request) with one control, the egress
proxy. The spec-to-PR helper's `run_tests` executes code the agent wrote, and that code could reach the network
through the proxy. This tool is the second control, in its own failure domain: the test run happens in a
container started with `--network=none`, so the code under test has a loopback interface and nothing else.

Dependencies are installed before the run, from the lock file with hashes, into a virtual environment built by
the same image (so its interpreter path and Python version match) and then mounted read-only by the test
container. The install step has the runner's network, which goes only through the egress proxy; it mounts the
lock file alone, never the agent's working copy, so nothing the agent wrote runs while the network is available.

    python tools/sandbox_run.py check                      # the policy's findings (exit 1 if any)
    python tools/sandbox_run.py install --repo R --venv V  # build the test venv INSIDE the same image (network on)
    python tools/sandbox_run.py command --repo R --venv V  # print the container command, do not run it
    python tools/sandbox_run.py run --repo R --venv V      # run it (CI only; needs a container runtime)

Rules (deploy/test-sandbox/policy.json, relay-test-sandbox-v1):

    SB001  the network is not "none"
    SB002  the image is not pinned by digest, or not the reviewed dev-container digest in supply-chain/images.json
    SB003  the root filesystem is writable, or a mount is not read-only
    SB004  the user is root, a capability is kept, or privilege escalation is allowed
    SB005  an environment variable outside the allowlist, or one whose name looks like a credential
    SB006  no timeout, process limit or memory limit
    SB007  the command is not the test command (`python -m pytest …`), or goes through a shell

`reachable` is a MODEL of what the container's code can connect to: with `--network=none`, only loopback. It
is what Lab 15.1's probe asks; the real check is the container runtime's own isolation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_FILE = ROOT / "deploy" / "test-sandbox" / "policy.json"
ENV_ALLOWED = {"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PATH"}
CREDENTIAL = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|AUTH", re.IGNORECASE)
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def load_policy(path: Path = POLICY_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reviewed_digest(root: Path = ROOT) -> str:
    images = json.loads((root / "supply-chain" / "images.json").read_text(encoding="utf-8"))["images"]
    entry = next(i for i in images if i["file"] == ".devcontainer/devcontainer.json")
    return f"{entry['reference']}@{entry['digest']}"


def check_policy(policy: dict, root: Path = ROOT) -> list[tuple[str, str]]:
    """(rule, message) for every problem, in rule order."""
    out: list[tuple[str, str]] = []
    if policy.get("network") != "none":
        out.append(("SB001", f"network must be none, not {policy.get('network')!r}"))
    image = str(policy.get("image", ""))
    if not DIGEST.search(image) or image != reviewed_digest(root):
        out.append(("SB002", "image must be the reviewed dev-container image, by digest"))
    mounts = policy.get("mounts", [])
    if policy.get("read_only_root") is not True or any(m.get("mode") != "ro" for m in mounts):
        out.append(("SB003", "root filesystem and every mount must be read-only (only tmpfs is writable)"))
    user = str(policy.get("user", "0"))
    if user.split(":")[0] in {"0", "root", ""} or policy.get("cap_drop") != ["ALL"] \
            or policy.get("no_new_privileges") is not True:
        out.append(("SB004", "run as a non-root user with every capability dropped and no privilege escalation"))
    env = policy.get("env", {})
    bad_env = sorted(k for k in env if k not in ENV_ALLOWED or CREDENTIAL.search(k))
    if bad_env:
        out.append(("SB005", "environment not allowed: " + ", ".join(bad_env)))
    if not all(isinstance(policy.get(k), (int, str)) and policy.get(k) for k in ("timeout_seconds", "pids_limit",
                                                                                 "memory")):
        out.append(("SB006", "timeout, process limit and memory limit are all required"))
    cmd = policy.get("command", [])
    if cmd[:3] != ["python", "-m", "pytest"] or any(c in {"sh", "bash", "-c"} for c in cmd):
        out.append(("SB007", "the command must be python -m pytest, with no shell"))
    return out


def command(policy: dict, repo: str, venv: str, targets: tuple[str, ...] = (), root: Path = ROOT,
            validate: bool = True) -> list[str]:
    """The container command for one test run. Refuses (ValueError) if the policy has any finding.

    `validate=False` builds the command a policy WOULD give, findings or not; only probes use it, to show what a
    weakened policy lets through. The CLI never passes it."""
    findings = check_policy(policy, root) if validate else []
    if findings:
        raise ValueError("; ".join(f"{r} {m}" for r, m in findings))
    argv = ["docker", "run", "--rm", f"--network={policy['network']}", "--read-only",
            f"--user={policy['user']}", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            f"--pids-limit={policy['pids_limit']}", f"--memory={policy['memory']}"]
    argv += [f"--tmpfs={t}" for t in policy.get("tmpfs", [])]
    sources = {"repo": repo, "venv": venv}
    argv += [f"--volume={sources[m['source']]}:{m['target']}:ro" for m in policy["mounts"]]
    argv += [f"--env={k}={v}" for k, v in sorted(policy.get("env", {}).items())]
    argv += ["--workdir=/src", policy["image"], *policy["command"], *targets]
    return argv


def install_command(policy: dict, repo: str, venv: str, root: Path = ROOT) -> list[str]:
    """The one networked step: create the venv inside the policy's image and install the lock file into it. Only
    requirements-dev.txt is mounted (read-only); the agent's code is not. pip refuses source builds and unhashed
    files (`--only-binary :all: --require-hashes`)."""
    findings = [f for f in check_policy(policy, root) if f[0] != "SB001"]
    if findings:
        raise ValueError("; ".join(f"{r} {m}" for r, m in findings))
    return ["docker", "run", "--rm", f"--user={policy['user']}", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--env=HTTPS_PROXY", "--env=PIP_INDEX_URL",  # the runner's proxy and the mirror, passed through
            f"--volume={repo}/requirements-dev.txt:/lock/requirements-dev.txt:ro", f"--volume={venv}:/venv",
            policy["image"], "sh", "-c",
            "python -m venv /venv && /venv/bin/python -m pip install --require-hashes --only-binary :all: "
            "-r /lock/requirements-dev.txt"]


def reachable(argv: list[str], host: str) -> bool:
    """MODEL: can code inside a container started with `argv` open a connection to `host`?"""
    if "--network=none" in argv:
        return host in LOOPBACK
    return True  # any other network mode reaches what the host can; the egress proxy is then the only control


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["check", "install", "command", "run"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--venv", default=".venv-test")
    ap.add_argument("targets", nargs="*")
    args = ap.parse_args(argv)
    policy = load_policy()
    if args.action == "check":
        findings = check_policy(policy)
        for rule, message in findings:
            print(f"{rule} {message}")
        print(f"{len(findings)} findings")
        return 1 if findings else 0
    try:
        if args.action == "install":
            return subprocess.run(install_command(policy, args.repo, args.venv), timeout=900).returncode
        cmd = command(policy, args.repo, args.venv, tuple(args.targets))
    except ValueError as exc:
        print(f"refused: {exc}")
        return 2
    if args.action == "command":
        print(" ".join(cmd))
        return 0
    return subprocess.run(cmd, timeout=int(policy["timeout_seconds"])).returncode


if __name__ == "__main__":
    sys.exit(main())

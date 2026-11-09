"""The generated data reproduces byte for byte, and Relay 4.26.0 in relay-repo/ is complete and passes its suite.

4.26.0 starts from canonical 4.25.0. The sets below are the exact files it adds and modifies, so a reviewer can
see that it leaves src/relay/service/, src/relay/store.py, src/relay/escalation/, src/relay/audit/ and infra/
alone.
"""

import json
import os
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, RELAY

CANONICAL = LAB_ROOT.parent.parent / "relay-baselines" / "4.25.0" / "relay-repo"
ADDED = {
    "deploy/egress-proxy/content-hosts.txt", "deploy/egress-proxy/content-urls.txt",
    "deploy/egress-proxy/splice-hosts.txt",
    "docs/adr/ADR-032-untrusted-ticket-text-and-rendering.md", "docs/adr/ADR-033-email-delivery-adapter.md",
    "docs/adr/ADR-034-taint-memory-and-compaction-defenses.md",
    "docs/adr/ADR-035-allowlisted-content-egress-path.md",
    "src/relay/delivery/__init__.py", "src/relay/delivery/email_smtp.py", "src/relay/render.py",
    "src/relay/worker/untrusted.py", "tests/test_agents_taint.py", "tests/test_delivery_email.py",
    "tests/test_infra_egress_content.py", "tests/test_render.py", "tests/test_worker_untrusted.py",
}
MODIFIED = {
    ".github/CODEOWNERS", "AGENTS.md", "deploy/egress-proxy/Containerfile", "deploy/egress-proxy/squid.conf",
    "governance/agents.json", "pyproject.toml", "src/relay/__init__.py", "src/relay/agents/__init__.py",
    "src/relay/agents/boundary.py", "src/relay/agents/contracts.py", "src/relay/agents/memory.py",
    "src/relay/agents/tools.py",
    "src/relay/api.py", "src/relay/worker/__init__.py", "src/relay/worker/runner.py", "src/relay/worker/triage.py",
    "tests/test_architecture.py", "tests/test_infra_egress.py", "tests/test_service_app.py",
    "tests/test_service_http.py", "tests/test_service_wsgi.py", "tests/test_worker_runner.py",
}
SUITE = 699


def same(a, b) -> bool:
    """Equal apart from line endings: the baselines are stored as checked in, and a checkout may convert."""
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == files(DATA_DIR)
    for rel in files(DATA_DIR):
        assert same(tmp_path / rel, DATA_DIR / rel), rel


def test_every_data_file_says_it_is_generated_and_no_payload_holds_instruction_text():
    for rel in sorted(files(DATA_DIR)):
        assert "GENERATED" in (DATA_DIR / rel).read_text(encoding="utf-8"), rel
    for cls in json.loads((DATA_DIR / "classes.json").read_text(encoding="utf-8"))["classes"]:
        assert cls["payload"] == (f"[[INJECTION technique={cls['technique']} effect={cls['effect']} "
                                  f"encoding={cls['encoding']}]]")


def test_relay_4_26_0_adds_and_modifies_exactly_the_listed_files():
    ours, base = files(RELAY), files(CANONICAL)
    assert ours - base == ADDED
    assert base - ours == set()
    assert {f for f in ours & base if not same(RELAY / f, CANONICAL / f)} == MODIFIED


def test_relay_suite_passes():
    env = {**os.environ, "PYTHONPATH": str(RELAY / "src")}
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY, env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout[-2000:]
    assert f"{SUITE} passed" in out.stdout

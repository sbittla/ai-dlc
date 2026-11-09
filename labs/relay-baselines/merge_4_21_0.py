"""Build the canonical Relay 4.21.0 from the two Batch 3 branches.

Chapter 8 (Relay 4.20.0) built the escalation engine, its HTTP routes, OpenAPI
contract and ADR-009 to ADR-011 on top of canonical 4.19.0. Chapter 11 (its own
4.21.0) added the non-production AWS environment: `infra/`, `deploy/`, the
shared limiter and WSGI entry point, their tests and ADR-012 to ADR-015. Both
started from canonical 4.19.0. Chapter 8 changed source and tests; Chapter 11
mostly added files. This script takes Chapter 8 as the base and applies
Chapter 11's additions deterministically:

    python labs/relay-baselines/merge_4_21_0.py

Output: labs/relay-baselines/4.21.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import shutil
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
CH8 = LABS / "ch08/L8.1-test-first-agent/solution/relay-repo"
CH11 = LABS / "ch11/L11.1-guardrailed-cloud-environment/relay-repo"
OUT = LABS / "relay-baselines/4.21.0/relay-repo"
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*")

CH11_DIRS = ["infra", "deploy"]
CH11_FILES = [
    "src/relay/service/sharedlimit.py",
    "src/relay/service/wsgi.py",
    "tests/test_infra_db_roles.py",
    "tests/test_infra_egress.py",
    "tests/test_service_sharedlimit.py",
    "tests/test_service_wsgi.py",
    "docs/adr/ADR-012-cloud-foundation-guardrails-iac.md",
    "docs/adr/ADR-013-private-network-and-egress.md",
    "docs/adr/ADR-014-managed-data-and-database-roles.md",
    "docs/adr/ADR-015-fargate-and-container-image.md",
]
VERSION_EDITS = {
    "pyproject.toml": ('version = "4.20.0"', 'version = "4.21.0"'),
    "src/relay/__init__.py": ('__version__ = "4.20.0"', '__version__ = "4.21.0"'),
    "tests/test_service_app.py": ('__version__ == "4.20.0"', '__version__ == "4.21.0"'),
    "tests/test_service_http.py": ('[1]["version"] == "4.20.0"', '[1]["version"] == "4.21.0"'),
}


def read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"anchor not found exactly once: {old!r}")
    return text.replace(old, new)


def main() -> None:
    for source in (CH8, CH11):
        if not source.is_dir():
            raise SystemExit(f"missing branch: {source}")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH8, OUT, ignore=IGNORE)

    for name in CH11_DIRS:
        shutil.copytree(CH11 / name, OUT / name, ignore=IGNORE)
    for name in CH11_FILES:
        if (OUT / name).exists():
            raise SystemExit(f"Chapter 11 file already exists in Chapter 8's tree: {name}")
        (OUT / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CH11 / name, OUT / name)

    for name, (old, new) in VERSION_EDITS.items():
        text, nl = read(OUT / name)
        write(OUT / name, replace_once(text, old, new), nl)

    agents, nl = read(OUT / "AGENTS.md")
    agents = replace_once(
        agents,
        "a background triage worker (4.19.0), and the escalation engine (4.20.0).",
        "a background triage worker (4.19.0), the escalation engine (4.20.0),\n"
        "and the OpenTofu configuration of its non-production AWS environment (4.21.0).",
    )
    agents = replace_once(
        agents,
        "- Decisions: `docs/adr/`.",
        "- `infra/`: OpenTofu for the non-production environment (ADR-012 to ADR-015); `infra/org/` holds the\n"
        "  organization's guardrails. `deploy/`: the container images. Plan only: `tofu plan`, then the policy checks.\n"
        "- Decisions: `docs/adr/`.",
    )
    push_rule = "- Never push to `main`, merge, or approve a pull request. A person reviews and merges every change.\n"
    agents = replace_once(
        agents,
        push_rule,
        push_rule
        + "- Never run `tofu apply`, `tofu destroy` or any command that changes a cloud account. A person applies a\n"
        "  reviewed plan from the protected CI environment.\n",
    )
    write(OUT / "AGENTS.md", agents, nl)

    owners, nl = read(OUT / ".github/CODEOWNERS")
    ch11_lines = [line for line in read(CH11 / ".github/CODEOWNERS")[0].splitlines()
                  if line.startswith(("/infra/", "/deploy/"))]
    owners = owners.rstrip("\n") + "\n" + "\n".join(ch11_lines) + "\n"
    write(OUT / ".github/CODEOWNERS", owners, nl)

    print(f"wrote canonical Relay 4.21.0 to {OUT}")


if __name__ == "__main__":
    main()

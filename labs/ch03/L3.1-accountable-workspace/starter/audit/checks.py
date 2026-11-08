"""The accountable-workspace checks (STARTER: implement the TODO functions).

Each check reads one part of a repository and returns a list of Findings.
Checks never modify the repository, never execute its code and never print a
secret: a finding about a secret shows only its first four characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .core import (Finding, finding, iter_files, load_json, markdown_sections, matches_any, read_text, redact,
                   rel)


def check_instructions(repo: Path, policy: dict) -> list[Finding]:
    """WS001–WS004: the agent instructions file.

    policy["instructions"] has: files (accepted names, in order of preference),
    required_sections, commands_section, required_commands, max_lines.

    - The first name in `files` that exists is the instructions file. If none
      exists: one WS001 finding with path files[0], and nothing else.
    - WS002 for each required section that is not a level-2 heading
      ("## Name", exact text), in the policy's order. Message: "missing section 'Name'".
    - WS003 if the file has more than max_lines lines (str.splitlines()).
      Message: "<n> lines; policy maximum is <max>".
    - WS004 for each required command with no bullet line "- <Command>: <something>"
      (case-insensitive, "*" bullets also accepted) inside the commands section.
      Message: "no '<command>' command". Only checked when the commands
      section exists; if it is missing, WS002 already reports it.
    """
    # TODO(L3.1): implement using the definition in the docstring.
    raise NotImplementedError('check_instructions')


def scan_secrets(repo: Path, policy: dict) -> list[Finding]:
    """WS010–WS011: secrets and forbidden files.

    policy["secrets"] has: patterns (list of {"id", "regex"}, in priority
    order), forbidden_files (globs matched against the file *name*),
    allowed_files (names exempt from forbidden_files), skip_dirs.

    For every file from iter_files(repo, skip_dirs), in that order:
    - WS011 if its name matches a forbidden glob and is not in allowed_files.
      Message: "forbidden file '<name>' is committed".
    - Then, if read_text() returns text, check each line (numbered from 1):
      the first pattern whose regex matches (re.search) gives one WS010
      finding for that line, with message "<pattern id>: <redact(match)>".
      At most one finding per line, so one secret is counted once.
    """
    # TODO(L3.1): implement using the definition in the docstring.
    raise NotImplementedError('scan_secrets')


def _mount_source(mount) -> str:
    if isinstance(mount, dict):
        return str(mount.get("source", ""))
    parts = dict(p.split("=", 1) for p in str(mount).split(",") if "=" in p)
    return parts.get("source", parts.get("src", ""))


def check_sandbox(repo: Path, policy: dict) -> list[Finding]:
    """WS020–WS023: the dev container that agents run in.

    policy["sandbox"] has: file, forbidden_mount_fragments,
    forbidden_run_args, require_image_digest.

    - WS020 if the file does not exist (and nothing else).
    - WS021 for each entry of "mounts" whose source contains any forbidden
      fragment. Mounts are either objects with a "source" key or strings like
      "source=X,target=Y,type=bind". Message: "mount source '<source>' exposes host credentials".
    - WS022 for each entry of "runArgs" that equals a forbidden argument or
      starts with it followed by "=" ; and once if "privileged" is true.
      Message: "run argument '<arg>'" (or "privileged: true").
    - WS023 if require_image_digest, the config has an "image", and the image
      does not contain "@sha256:". Message: "image '<image>' is pinned by tag, not digest".
    """
    # TODO(L3.1): implement using the definition in the docstring.
    raise NotImplementedError('check_sandbox')


def check_branch_protection(repo: Path, policy: dict) -> list[Finding]:
    """WS030–WS036: branch protection (from an exported JSON file) and CODEOWNERS.

    policy["branch_protection"] has: file, codeowners (candidate paths),
    min_approving_reviews, require_code_owner_reviews, required_status_checks,
    enforce_admins, allow_force_pushes. The export uses the shape of GitHub's
    branch-protection API response.

    - WS030 if the export is missing; otherwise:
      - WS031 if required_pull_request_reviews.required_approving_review_count
        (0 when absent or null) is below the minimum. Message: "<n> required; policy minimum is <min>".
      - WS032 if the policy requires code-owner reviews and
        required_pull_request_reviews.require_code_owner_reviews is not true.
      - WS033 for each policy status check missing from
        required_status_checks.contexts (in policy order). Message: "status check '<name>' not required".
      - WS034 if the policy requires enforce_admins and enforce_admins.enabled is not true.
      - WS035 if the policy forbids force pushes and allow_force_pushes.enabled is true.
    - WS036 (whether or not the export exists) if none of the codeowners paths
      exists; path is the first candidate.
    """
    # TODO(L3.1): implement using the definition in the docstring.
    raise NotImplementedError('check_branch_protection')


def check_mcp(repo: Path, policy: dict) -> list[Finding]:
    """WS040–WS041: MCP servers configured for agents in this repository.

    policy["mcp"] has: file, allowlist ({server name: {"command", "args"}}).
    The file has the shape {"mcpServers": {name: {"command", "args", ...}}}.

    - No file: no findings (a repository need not configure MCP servers).
    - For each server, in sorted name order:
      - WS040 if its name is not on the allowlist. Message: "server '<name>' is not allowlisted".
      - WS041 if it is, but its command or args (args default []) differ from
        the pinned ones. Message: "server '<name>' launch differs from the pinned command".
    """
    # TODO(L3.1): implement using the definition in the docstring.
    raise NotImplementedError('check_mcp')


def apply_waivers(findings: list[Finding], waivers: list[dict], policy: dict,
                  as_of: date) -> tuple[list[Finding], list[Finding]]:
    """Split findings into (open, waived).

    A waiver is {"check", "path", "reason", "owner", "expires" (YYYY-MM-DD)}.
    A finding is waived only if some waiver has the same check and path,
    a non-empty owner and reason, an expiry on or after `as_of`, and the
    finding's severity is in policy["waivers"]["waivable_severities"].
    Critical and high findings can never be waived under the book's policy.
    Both lists keep the input order.
    """
    # TODO(L3.1): implement using the definition in the docstring.
    raise NotImplementedError('apply_waivers')


# ----------------------------------------------------------------- provided

CHECK_FUNCTIONS = (check_instructions, scan_secrets, check_sandbox, check_branch_protection, check_mcp)


@dataclass(frozen=True)
class AuditResult:
    repo: str
    open: tuple[Finding, ...]
    waived: tuple[Finding, ...]


def run_audit(repo: Path, policy: dict, as_of: date) -> AuditResult:
    """Run every check, apply the repository's waivers, and sort by severity."""
    repo = Path(repo)
    findings = [f for check in CHECK_FUNCTIONS for f in check(repo, policy)]
    waivers = (load_json(repo / policy["waivers"]["file"]) or {}).get("waivers", [])
    open_, waived = apply_waivers(findings, waivers, policy, as_of)
    return AuditResult(repo.name, tuple(sorted(open_, key=Finding.sort_key)),
                       tuple(sorted(waived, key=Finding.sort_key)))

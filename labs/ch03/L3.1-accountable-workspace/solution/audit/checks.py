"""The accountable-workspace checks (reference solution).

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
    cfg = policy["instructions"]
    path = next((repo / name for name in cfg["files"] if (repo / name).is_file()), None)
    if path is None:
        return [finding("WS001", cfg["files"][0], "no agent instructions file")]
    name = rel(repo, path)
    text = path.read_text(encoding="utf-8")
    sections = markdown_sections(text)
    out = [finding("WS002", name, f"missing section '{s}'") for s in cfg["required_sections"] if s not in sections]
    n_lines = len(text.splitlines())
    if n_lines > cfg["max_lines"]:
        out.append(finding("WS003", name, f"{n_lines} lines; policy maximum is {cfg['max_lines']}"))
    commands = sections.get(cfg["commands_section"])
    if commands is not None:
        for cmd in cfg["required_commands"]:
            if not re.search(rf"^\s*[-*]\s*{re.escape(cmd)}\s*:\s*\S", commands, re.IGNORECASE | re.MULTILINE):
                out.append(finding("WS004", name, f"no '{cmd}' command"))
    return out


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
    cfg = policy["secrets"]
    patterns = [(p["id"], re.compile(p["regex"])) for p in cfg["patterns"]]
    out = []
    for path in iter_files(repo, cfg["skip_dirs"]):
        name = path.name
        where = rel(repo, path)
        if matches_any(name, cfg["forbidden_files"]) and name not in cfg["allowed_files"]:
            out.append(finding("WS011", where, f"forbidden file '{name}' is committed"))
        text = read_text(path)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for pid, rx in patterns:
                m = rx.search(line)
                if m:
                    out.append(finding("WS010", where, f"{pid}: {redact(m.group(0))}", line=n))
                    break
    return out


def _parse_mount(mount) -> tuple[str, str]:
    """(type, source) of a devcontainer mount; a string without type= counts as a bind mount."""
    if isinstance(mount, dict):
        return str(mount.get("type", "bind")), str(mount.get("source", ""))
    parts = dict(p.split("=", 1) for p in str(mount).split(",") if "=" in p)
    return parts.get("type", "bind"), parts.get("source", parts.get("src", ""))


def check_sandbox(repo: Path, policy: dict) -> list[Finding]:
    """WS020–WS023: the dev container that agents run in. Mounts and run arguments are allowlisted.

    policy["sandbox"] has: file, allowed_mount_types, mount_run_args,
    allowed_run_args, require_image_digest.

    - WS020 if the file does not exist (and nothing else).
    - WS021 for each entry of "mounts" whose type is not in allowed_mount_types
      (named volumes and tmpfs hold no host files; a bind mount exposes the host).
      Mounts are objects with "type" and "source", or strings like
      "source=X,target=Y,type=bind"; a missing type counts as "bind".
      Message: "host path '<source>' is mounted (type <type>)".
    - In "runArgs", in order:
      - an argument in mount_run_args ("-v", "--volume", "--mount") is a mount:
        WS021 with the next argument as its value, which is then skipped;
        "<flag>=<value>" is the same. Message: "run argument mounts '<value>'".
      - any other argument not in allowed_run_args: WS022, message "run argument '<arg>'".
    - WS022 once more if "privileged" is true. Message: "privileged: true".
    - WS023 if require_image_digest, the config has an "image", and the image
      does not contain "@sha256:". Message: "image '<image>' is pinned by tag, not digest".
    """
    cfg = policy["sandbox"]
    data = load_json(repo / cfg["file"])
    if data is None:
        return [finding("WS020", cfg["file"], "no dev container configuration")]
    out = []
    for mount in data.get("mounts", []):
        kind, source = _parse_mount(mount)
        if kind not in cfg["allowed_mount_types"]:
            out.append(finding("WS021", cfg["file"], f"host path '{source}' is mounted (type {kind})"))
    args = list(data.get("runArgs", []))
    i = 0
    while i < len(args):
        arg = args[i]
        flag, _, value = arg.partition("=")
        if flag in cfg["mount_run_args"]:
            if not value:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            out.append(finding("WS021", cfg["file"], f"run argument mounts '{value}'"))
        elif arg not in cfg["allowed_run_args"]:
            out.append(finding("WS022", cfg["file"], f"run argument '{arg}'"))
        i += 1
    if data.get("privileged") is True:
        out.append(finding("WS022", cfg["file"], "privileged: true"))
    image = data.get("image")
    if cfg["require_image_digest"] and image and "@sha256:" not in image:
        out.append(finding("WS023", cfg["file"], f"image '{image}' is pinned by tag, not digest"))
    return out


def check_branch_protection(repo: Path, policy: dict) -> list[Finding]:
    """WS030–WS037: branch protection (from an exported JSON file) and CODEOWNERS.

    policy["branch_protection"] has: file, codeowners (candidate paths),
    min_approving_reviews, require_code_owner_reviews, required_status_checks,
    enforce_admins, allow_force_pushes, fresh_approval_settings. The export uses
    the shape of GitHub's branch-protection API response. A committed export is
    self-attested: in CI, fetch the live settings from the platform's API instead.

    - WS030 if the export is missing; otherwise:
      - WS031 if required_pull_request_reviews.required_approving_review_count
        (0 when absent or null) is below the minimum. Message: "<n> required; policy minimum is <min>".
      - WS032 if the policy requires code-owner reviews and
        required_pull_request_reviews.require_code_owner_reviews is not true.
      - WS033 for each policy status check missing from
        required_status_checks.contexts (in policy order). Message: "status check '<name>' not required".
      - WS034 if the policy requires enforce_admins and enforce_admins.enabled is not true.
      - WS035 if the policy forbids force pushes and allow_force_pushes.enabled is true.
      - WS037 for each name in fresh_approval_settings (in policy order) that is not
        true in required_pull_request_reviews. Message: "'<name>' is not enabled".
        Without them, an approval given before a later push still counts.
    - WS036 (whether or not the export exists) if none of the codeowners paths
      exists; path is the first candidate.
    """
    cfg = policy["branch_protection"]
    out = []
    bp = load_json(repo / cfg["file"])
    if bp is None:
        out.append(finding("WS030", cfg["file"], "no branch protection export"))
    else:
        reviews = bp.get("required_pull_request_reviews") or {}
        count = reviews.get("required_approving_review_count") or 0
        if count < cfg["min_approving_reviews"]:
            out.append(finding("WS031", cfg["file"], f"{count} required; policy minimum is {cfg['min_approving_reviews']}"))
        if cfg["require_code_owner_reviews"] and reviews.get("require_code_owner_reviews") is not True:
            out.append(finding("WS032", cfg["file"], "code-owner review not required"))
        contexts = (bp.get("required_status_checks") or {}).get("contexts") or []
        for check in cfg["required_status_checks"]:
            if check not in contexts:
                out.append(finding("WS033", cfg["file"], f"status check '{check}' not required"))
        if cfg["enforce_admins"] and (bp.get("enforce_admins") or {}).get("enabled") is not True:
            out.append(finding("WS034", cfg["file"], "protection does not apply to administrators"))
        if not cfg["allow_force_pushes"] and (bp.get("allow_force_pushes") or {}).get("enabled") is True:
            out.append(finding("WS035", cfg["file"], "force pushes to the protected branch are allowed"))
        for name in cfg["fresh_approval_settings"]:
            if reviews.get(name) is not True:
                out.append(finding("WS037", cfg["file"], f"'{name}' is not enabled"))
    if not any((repo / p).is_file() for p in cfg["codeowners"]):
        out.append(finding("WS036", cfg["codeowners"][0], "no CODEOWNERS file"))
    return out


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
    cfg = policy["mcp"]
    data = load_json(repo / cfg["file"])
    if data is None:
        return []
    out = []
    for name in sorted(data.get("mcpServers", {})):
        server = data["mcpServers"][name]
        pinned = cfg["allowlist"].get(name)
        if pinned is None:
            out.append(finding("WS040", cfg["file"], f"server '{name}' is not allowlisted"))
        elif server.get("command") != pinned["command"] or server.get("args", []) != pinned["args"]:
            out.append(finding("WS041", cfg["file"], f"server '{name}' launch differs from the pinned command"))
    return out


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
    allowed = set(policy["waivers"]["waivable_severities"])

    def covered(f: Finding) -> bool:
        if f.severity not in allowed:
            return False
        for w in waivers:
            if (w.get("check") == f.check and w.get("path") == f.path
                    and str(w.get("owner", "")).strip() and str(w.get("reason", "")).strip()
                    and date.fromisoformat(w["expires"]) >= as_of):
                return True
        return False

    open_, waived = [], []
    for f in findings:
        (waived if covered(f) else open_).append(f)
    return open_, waived


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

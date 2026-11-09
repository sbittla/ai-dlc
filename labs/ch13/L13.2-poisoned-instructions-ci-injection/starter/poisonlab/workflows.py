"""A linter for GitHub Actions workflows that run agents on untrusted events (TODO 3 in starter/).

    WF001  an untrusted trigger with write permissions (none declared, write-all, or contents, pull-requests,
           actions, packages or workflows: write)
    WF002  untrusted event text in a run: script or in an action's with: input (script or prompt injection)
    WF003  pull_request_target checking out the pull request's head
    WF004  an action not pinned to a full commit SHA
    WF005  a secret passed to a step of a workflow with an untrusted trigger
    WF006  a comment trigger with no author_association check in an if:
    WF007  an agent given shell, push or web tools on an untrusted trigger

The reader below handles the subset of YAML the lab's workflows use (block mappings, block sequences,
inline lists, folded and literal scalars). Real projects should use a maintained linter such as actionlint
or zizmor as well; this one exists to show what such tools look for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

UNTRUSTED_TRIGGERS = {"pull_request_target", "issue_comment", "issues", "discussion", "discussion_comment",
                      "workflow_run", "pull_request_review", "pull_request_review_comment"}
# Event fields an outsider can write, including inside a function such as format() or toJSON(). Partial: use
# actionlint or zizmor as well.
UNTRUSTED_TEXT = re.compile(r"\$\{\{(?:(?!\}\}).)*\b(github\.event\.(comment\.body|issue\.title|issue\.body|"
                            r"pull_request\.title|pull_request\.body|pull_request\.head\.ref|pull_request\.head\.label|"
                            r"review\.body|review_comment\.body|discussion\.title|discussion\.body|head_commit\.message|"
                            r"commits|workflow_run\.head_branch|workflow_run\.head_commit\.message)|github\.head_ref|"
                            r"toJSON\(github\.event\))(?:(?!\}\}).)*\}\}")
WRITE_SCOPES = {"contents", "pull-requests", "actions", "packages", "workflows"}
RISKY_TOOLS = {"bash", "gitpush", "webfetch"}
SHA = re.compile(r"@[0-9a-f]{40}$")


@dataclass(frozen=True)
class Finding:
    rule: str
    line: int
    message: str


@dataclass
class Step:
    line: int
    uses: str | None = None
    run: list[tuple[int, str]] = field(default_factory=list)    # script lines
    with_: list[tuple[int, str, str]] = field(default_factory=list)  # (line, key, value)
    env: list[tuple[int, str, str]] = field(default_factory=list)


def triggers(text: str) -> set[str]:
    """Provided: the event names under `on:`."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^on:\s*(.*)$", ln)
        if not m:
            continue
        rest = m[1].strip()
        if rest.startswith("["):
            return {t.strip() for t in rest.strip("[]").split(",") if t.strip()}
        if rest:
            return {rest}
        out = set()
        for nxt in lines[i + 1:]:
            if nxt and not nxt.startswith(" "):
                break
            k = re.match(r"^  ([a-z_]+):", nxt)
            if k:
                out.add(k[1])
        return out
    return set()


def permissions(text: str) -> list[tuple[int, dict[str, str] | str]]:
    """Provided: every permissions: block, as (line, {scope: level}) or (line, "write-all")."""
    out, lines = [], text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)permissions:\s*(.*)$", ln)
        if not m:
            continue
        if m[2].strip():
            out.append((i + 1, m[2].strip()))
            continue
        indent, block = len(m[1]), {}
        for nxt in lines[i + 1:]:
            k = re.match(r"^(\s*)([a-z-]+):\s*(\S+)", nxt)
            if not k or len(k[1]) <= indent:
                break
            block[k[2]] = k[3]
        out.append((i + 1, block))
    return out


def steps(text: str) -> list[Step]:
    """Provided: the steps of every job, with their uses, run script, with: and env: entries."""
    out: list[Step] = []
    lines = text.splitlines()
    cur, section, base, sec_indent = None, None, 0, 0
    for n, ln in enumerate(lines, 1):
        m = re.match(r"^(\s*)- (uses|name|run):\s*(.*)$", ln)
        if m and (cur is None or len(m[1]) <= base):
            cur, base, section = Step(n), len(m[1]), None
            out.append(cur)
            ln = " " * (base + 2) + f"{m[2]}: {m[3]}"
        if cur is None:
            continue
        indent = len(ln) - len(ln.lstrip())
        if ln.strip() and indent <= base and not ln.lstrip().startswith("- "):
            cur = None
            continue
        k = re.match(r"^\s*([A-Za-z_][\w-]*):\s*(.*)$", ln)
        if section and indent > sec_indent:
            if section == "run":
                cur.run.append((n, ln.strip()))
            elif k:
                getattr(cur, section).append((n, k[1], k[2]))
            continue
        section = None
        if not k:
            continue
        key, value = k[1], k[2].strip()
        if key == "uses":
            cur.uses = value.split("#")[0].strip()
        elif key == "run":
            section, sec_indent = ("run", indent) if value in ("|", ">", "|-", ">-") else (None, indent)
            if section is None:
                cur.run.append((n, value))
        elif key in ("with", "env"):
            if value.startswith("{"):
                for part in value.strip("{}").split(","):
                    if ":" in part:
                        a, b = part.split(":", 1)
                        getattr(cur, "with_" if key == "with" else "env").append((n, a.strip(), b.strip()))
            else:
                section, sec_indent = ("with_" if key == "with" else "env"), indent
    return out


def lint(text: str) -> list[Finding]:
    """All findings for one workflow, sorted by (line, rule). At most one finding per rule per line.

    - WF001: if the workflow has an untrusted trigger and (no permissions block at all, or any block is the
      string "write-all", or any block gives "write" to a scope in WRITE_SCOPES): one finding at the first
      permissions block's line, or line 1 if there is none.
    - WF002: each run line, and each with: value, matching UNTRUSTED_TEXT. (env: values are the safe way to
      pass text, and if: conditions are not executed as code, so neither is reported.)
    - WF003: with pull_request_target among the triggers, a checkout step whose with: ref mentions
      "pull_request.head".
    - WF004: each step whose uses is not a local path ("./") and does not end in a 40-hex commit SHA.
    - WF005: with an untrusted trigger, each with: or env: value containing "secrets.".
    - WF006: with issue_comment, discussion_comment or pull_request_review_comment among the triggers, and no
      line of the file containing both "if:" (or a folded if: block) and "author_association": one finding
      at line 1. Search the whole text for "author_association" for simplicity.
    - WF007: with an untrusted trigger, each with: value of key allowed_tools that names any RISKY_TOOLS
      (compare lower-case names with commas and spaces removed).
    """
    raise NotImplementedError("TODO 3: the workflow linter WF001-WF007")

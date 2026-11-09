"""The pull-request check: what a machine can see before a person reviews (Lab 9.1).

A record is a pull request: its commits, in order, each with the files it
changed (path, status A/M/D, added and removed line counts, and the changed
lines themselves where known). `check_pr` returns findings; a blocking one
means the pull request is not ready for review. The check cannot tell whether
the code is right. It tells the reviewer where to look, and refuses changes
too large or too tangled to review.

| Code | Finding | Blocking |
| --- | --- | --- |
| PR01 | More than 200 changed lines outside tests/, or more than 400 in all | yes |
| PR02 | A commit changes code and a test that existed before the pull request | yes |
| PR03 | Code changes with no tests-only commit before them | yes |
| PR04 | A migration with no migration test in the pull request | yes |
| PR05 | A route added with no change to an OpenAPI description | yes |
| PR06 | The prose spec and code changed in one pull request | yes |
| PR07 | `# oracle:` markers or `@for_all` properties added, changed or removed | warning |
| PR08 | Reviewed at more than 500 changed lines per hour | warning |
| PR09 | Code changed, with no docs change and no "Docs:" line in the description | warning |
| PR10 | No independent reviewer: every reviewer opened the pull request or wrote one of its commits | yes |

"Code" is anything under src/ or migrations/. "Tests" is anything under tests/.
A commit author written "agent (name)" is the person who ran the agent. A record
with no reviewers, or no "opened_by", is checked on what it has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .diffs import FileChange, from_record

MAX_CODE_LINES = 200
MAX_TOTAL_LINES = 400
MAX_LINES_PER_HOUR = 500
BLOCKING = {"PR01", "PR02", "PR03", "PR04", "PR05", "PR06", "PR10"}
ROUTE = re.compile(r"""\(\s*["'](GET|POST|PUT|DELETE|PATCH)["']\s*,\s*["']/v1/""")
MIGRATION_SQL = re.compile(r"\b(DROP|ALTER)\s+TABLE\b", re.IGNORECASE)
MARKER = re.compile(r"#\s*oracle:|@for_all\b")


@dataclass(frozen=True)
class Finding:
    code: str
    message: str

    @property
    def blocking(self) -> bool:
        return self.code in BLOCKING


def is_test(path: str) -> bool:
    return path.startswith("tests/")


def is_code(path: str) -> bool:
    return path.startswith("src/") or path.startswith("migrations/")


def is_docs(path: str) -> bool:
    return path.startswith("docs/") or path.startswith("specs/") or path in ("AGENTS.md", "README.md")


def is_migration(change: FileChange) -> bool:
    return is_code(change.path) and ("migrat" in change.path or any(MIGRATION_SQL.search(line)
                                                                    for line in change.added_lines))


def commits(record: dict) -> list[list[FileChange]]:
    """The record's commits, in order, as lists of FileChange."""
    return [[from_record(f) for f in c["files"]] for c in record["commits"]]


def all_changes(record: dict) -> list[FileChange]:
    return [c for commit in commits(record) for c in commit]


def sizes(record: dict) -> tuple[int, int]:
    """(changed lines outside tests/, changed lines in all)."""
    changes = all_changes(record)
    return sum(c.changed for c in changes if not is_test(c.path)), sum(c.changed for c in changes)


def check_pr(record: dict) -> list[Finding]:
    """Findings for one pull-request record, in code order (PR01 first)."""
    findings: list[Finding] = []
    changes = all_changes(record)
    code, total = sizes(record)
    if code > MAX_CODE_LINES or total > MAX_TOTAL_LINES:
        findings.append(Finding("PR01", f"{code} changed lines outside tests/ and {total} in all; the limits are "
                                        f"{MAX_CODE_LINES} and {MAX_TOTAL_LINES}"))

    edited = sorted({c.path for commit in commits(record) if any(is_code(x.path) for x in commit)
                     for c in commit if is_test(c.path) and c.status != "A"})
    if edited:
        findings.append(Finding("PR02", f"{len(edited)} existing test file(s) changed in a commit that changes code: "
                                        + ", ".join(edited)))

    first_code = next((i for i, commit in enumerate(commits(record)) if any(is_code(c.path) for c in commit)), None)
    if first_code is not None and not any(all(is_test(c.path) for c in commit)
                                          for commit in commits(record)[:first_code]):
        findings.append(Finding("PR03", "code changes with no tests-only commit before them"))

    migrations = [c.path for c in changes if is_migration(c)]
    if migrations and not any(is_test(c.path) and "migrat" in c.path for c in changes):
        findings.append(Finding("PR04", "migration without a migration test: " + ", ".join(migrations)))

    if any(ROUTE.search(line) for c in changes if is_code(c.path) for line in c.added_lines) \
            and not any(c.path.endswith(".openapi.json") for c in changes):
        findings.append(Finding("PR05", "a route is added and no OpenAPI description changes"))

    if any(c.path.startswith("specs/") and c.path.endswith("/spec.md") for c in changes) \
            and any(is_code(c.path) for c in changes):
        findings.append(Finding("PR06", "the spec and the code change in one pull request"))

    marked = sorted({c.path for c in changes if is_test(c.path)
                     and any(MARKER.search(line) for line in c.added_lines + c.removed_lines)})
    if marked:
        findings.append(Finding("PR07", "oracle markers or properties changed; a code owner of the tests must "
                                        "review each: " + ", ".join(marked)))

    minutes = record.get("review", {}).get("minutes")
    if minutes and total / (minutes / 60) > MAX_LINES_PER_HOUR:
        findings.append(Finding("PR08", f"reviewed at {round(total / (minutes / 60)):,} changed lines per hour; "
                                        f"the guide is at most {MAX_LINES_PER_HOUR}"))

    if any(is_code(c.path) for c in changes) and not any(is_docs(c.path) for c in changes) \
            and not re.search(r"^Docs:|\bDocs:", record.get("description", ""), re.M):
        findings.append(Finding("PR09", "code changes with no docs change and no 'Docs:' line in the description"))

    reviewers = record.get("review", {}).get("reviewers", [])
    involved = {person(c["author"]) for c in record["commits"]} | {record.get("opened_by")}
    if reviewers and not [r for r in reviewers if r not in involved]:
        findings.append(Finding("PR10", "no independent reviewer: " + ", ".join(reviewers)
                                + " opened the pull request or wrote one of its commits"))
    return findings


def person(author: str) -> str:
    """'agent (priya.n)' -> 'priya.n': the person accountable for an agent's commit."""
    return author[author.index("(") + 1:author.rindex(")")] if author.startswith("agent (") else author


def required_owners(record: dict, rules: list) -> list[str]:
    """Every code-owner team that must approve: one owner from each matched line (codeowners.owners_for)."""
    from .codeowners import owners_for

    return sorted({" or ".join(owners_for(rules, c.path)) for c in all_changes(record) if owners_for(rules, c.path)})

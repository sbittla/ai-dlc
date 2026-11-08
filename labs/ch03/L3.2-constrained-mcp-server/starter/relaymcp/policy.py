"""The query policy: pure functions that decide what an agent may read (STARTER: implement the TODO functions).

Nothing in this module trusts the caller. A request is untrusted input from a
model, which may itself have read untrusted input (Chapter 2). The policy
accepts only allowlisted templates with typed, bounded parameters, binds every
value through SQLite, caps the rows returned, redacts personal data, and
writes an audit entry for every call, accepted or not.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from .templates import (ALLOWED_TABLES, DEFAULT_LIMIT, MAX_LIMIT, MAX_REQUEST_BYTES, PII_COLUMNS, SECRET_COLUMNS,
                        TEMPLATES, Template)

REQUEST_FIELDS = ("template", "params", "limit")


class PolicyError(Exception):
    """A request the policy refuses. `code` is stable and is what the audit log records."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedRequest:
    template: str
    params: dict  # every parameter the template declares; absent optional ones are None
    limit: int


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: list[dict]
    truncated: bool  # True when more rows matched than the limit allowed


def canonical(request) -> bytes:
    """The bytes a request is measured and hashed by: raw text as UTF-8, or any other JSON
    value (an object from an MCP client, say) as compact, sorted JSON."""
    if isinstance(request, str):
        return request.encode("utf-8")
    return json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def validate_request(request: str | dict, templates: dict[str, Template] = TEMPLATES) -> ValidatedRequest:
    """Check a request against the allowlist, or raise PolicyError. Checks run in this order:

    1. len(canonical(request)) > MAX_REQUEST_BYTES       -> "request_too_large"
    2. a str that is not valid JSON                         -> "invalid_json"
    3. not a JSON object (dict)                             -> "invalid_request"
    4. any key other than template, params, limit           -> "unknown_field" (first in sorted order)
    5. template not a str, or not in `templates`            -> "unknown_template"
    6. params (default {}) not a dict                       -> "invalid_request"
    7. a parameter the template does not declare            -> "unknown_param" (first in sorted order)
    8. each declared parameter, in declaration order:
         absent and required                                -> "missing_param"; absent optional -> None
         int:  type must be exactly int (bool is rejected)  -> "bad_type"; outside [min, max] -> "out_of_range"
         enum: must be a str                                -> "bad_type"; not in choices     -> "bad_value"
         date: a str matching YYYY-MM-DD that is a real date, else "bad_type"
         str:  must be a str                                -> "bad_type"; longer than max_len -> "too_long";
               any control character (code point < 32, or 127) -> "bad_value"
    9. limit (default DEFAULT_LIMIT): type exactly int, else "bad_type"; < 1 -> "out_of_range";
       > MAX_LIMIT -> "limit_exceeded"
    """
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('validate_request')


def _check_param(name: str, p, value):
    """Return `value` if it satisfies rule 8 of validate_request for parameter `p`, else raise PolicyError."""
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('_check_param')


def escape_like(text: str) -> str:
    """Escape text for a LIKE pattern with ESCAPE '\\': backslash first, then % and _."""
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('escape_like')


def run_template(conn: sqlite3.Connection, req: ValidatedRequest,
                 templates: dict[str, Template] = TEMPLATES) -> QueryResult:
    """Run a validated request with bound parameters and return at most req.limit rows.

    - Bind every declared parameter by name. A `like` parameter is bound as
      "%" + escape_like(value) + "%" so that % and _ in the value match only themselves.
    - Call conn.reset_budget() first if the connection has it (db.ReadOnlyConnection).
    - Fetch at most limit + 1 rows: if more than `limit` came back, set truncated
      and return only the first `limit`.
    - Rows are dicts keyed by the column names from cursor.description.
    """
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('run_template')


def redact_row(row: dict, pii: dict[str, str] = PII_COLUMNS) -> tuple[dict, int]:
    """A copy of `row` with every non-None value in a PII column replaced by its marker,
    and the number of values replaced. The input row is not modified."""
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('redact_row')


def lint_templates(templates: dict[str, Template] = TEMPLATES, allowed_tables=ALLOWED_TABLES,
                   secret_columns=SECRET_COLUMNS) -> list[str]:
    """Problems with the allowlist itself, as "<template>: <problem>" strings, in template order.

    For each template, check in this order and report every problem found:
    - "not a single SELECT": the SQL does not start with SELECT (case-insensitive) or contains ";"
    - "selects *": the SQL contains "*" (a future secret column would leak)
    - "string formatting": the SQL contains "{", "%s" or a positional "?"
    - "undeclared parameter :x" for each :name in the SQL the template does not declare (sorted)
    - "unused parameter x" for each declared parameter the SQL never uses (declaration order)
    - "table not allowlisted: t" for each table after FROM or JOIN that is not allowed (in SQL order)
    - "secret column: c" for each secret column named anywhere in the SQL (sorted)
    """
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('lint_templates')


# ----------------------------------------------------------------- audit (provided)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuditLog:
    """Append-only audit entries, in memory and optionally as JSON lines in a file."""

    def __init__(self, path: Path | None = None, clock: Callable[[], str] = utc_now) -> None:
        self.path = Path(path) if path else None
        self.clock = clock
        self.entries: list[dict] = []

    def record(self, **fields) -> None:
        entry = {"at": self.clock(), **fields}
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
        self.entries.append(entry)


def handle(request: str | dict, conn: sqlite3.Connection, audit: AuditLog, caller: str = "unknown",
           templates: dict[str, Template] = TEMPLATES) -> dict:
    """Serve one request. Never raises; writes exactly one audit entry before it returns.

    Response on success:
      {"ok": True, "template", "columns" (list), "rows" (redacted), "row_count", "truncated", "redacted_values"}
    Response on refusal: {"ok": False, "error": <PolicyError code>, "message": <its message>}
    Response if SQLite fails (including the step budget): {"ok": False, "error": "query_failed",
      "message": "the query could not be completed"}  (never the SQLite error text)

    The audit entry has: caller, request_sha256 (hex digest of canonical(request)),
    request_bytes, outcome ("ok" or the error code), template and params (the
    validated values; None if validation failed), limit, rows, truncated,
    redacted_values (0, 0, False, 0 when refused). The raw request is never logged.
    If audit.record raises, fail closed: return
      {"ok": False, "error": "audit_failed", "message": "the call could not be audited"} and no rows.
    """
    # TODO(L3.2): implement using the definition in the docstring.
    raise NotImplementedError('handle')

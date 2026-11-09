"""The query policy: pure functions that decide what an agent may read (reference solution).

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
    size = len(canonical(request))
    if size > MAX_REQUEST_BYTES:
        raise PolicyError("request_too_large", f"{size} bytes; the maximum is {MAX_REQUEST_BYTES}")
    if isinstance(request, str):
        try:
            request = json.loads(request)
        except json.JSONDecodeError:
            raise PolicyError("invalid_json", "the request is not valid JSON") from None
    if not isinstance(request, dict):
        raise PolicyError("invalid_request", "the request must be a JSON object")
    extra = sorted(set(request) - set(REQUEST_FIELDS))
    if extra:
        raise PolicyError("unknown_field", f"unknown field {extra[0]!r}")
    name = request.get("template")
    if not isinstance(name, str) or name not in templates:
        raise PolicyError("unknown_template", "not an allowlisted template")
    template = templates[name]
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise PolicyError("invalid_request", "params must be an object")
    unknown = sorted(set(params) - set(template.params))
    if unknown:
        raise PolicyError("unknown_param", f"unknown parameter {unknown[0]!r} for template {name!r}")
    clean = {}
    for pname, p in template.params.items():
        if pname not in params:
            if p.required:
                raise PolicyError("missing_param", f"missing parameter {pname!r}")
            clean[pname] = None
            continue
        clean[pname] = _check_param(pname, p, params[pname])
    limit = request.get("limit", DEFAULT_LIMIT)
    if type(limit) is not int:
        raise PolicyError("bad_type", "limit must be an integer")
    if limit < 1:
        raise PolicyError("out_of_range", "limit must be at least 1")
    if limit > MAX_LIMIT:
        raise PolicyError("limit_exceeded", f"limit {limit} is above the maximum of {MAX_LIMIT}")
    return ValidatedRequest(name, clean, limit)


def _check_param(name: str, p, value):
    """Return `value` if it satisfies rule 8 of validate_request for parameter `p`, else raise PolicyError."""
    if p.type == "int":
        if type(value) is not int:
            raise PolicyError("bad_type", f"{name!r} must be an integer")
        if (p.min is not None and value < p.min) or (p.max is not None and value > p.max):
            raise PolicyError("out_of_range", f"{name!r} must be between {p.min} and {p.max}")
        return value
    if p.type == "enum":
        if not isinstance(value, str):
            raise PolicyError("bad_type", f"{name!r} must be a string")
        if value not in p.choices:
            raise PolicyError("bad_value", f"{name!r} must be one of {', '.join(p.choices)}")
        return value
    if p.type == "date":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise PolicyError("bad_type", f"{name!r} must be a date, YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise PolicyError("bad_type", f"{name!r} must be a date, YYYY-MM-DD") from None
        return value
    if p.type == "str":
        if not isinstance(value, str):
            raise PolicyError("bad_type", f"{name!r} must be a string")
        if p.max_len is not None and len(value) > p.max_len:
            raise PolicyError("too_long", f"{name!r} is longer than {p.max_len} characters")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise PolicyError("bad_value", f"{name!r} contains a control character")
        return value
    raise ValueError(f"unknown parameter type {p.type!r}")


def escape_like(text: str) -> str:
    """Escape text for a LIKE pattern with ESCAPE '\\': backslash first, then % and _."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    template = templates[req.template]
    bind = {}
    for name, p in template.params.items():
        value = req.params[name]
        bind[name] = "%" + escape_like(value) + "%" if p.like and value is not None else value
    if hasattr(conn, "reset_budget"):
        conn.reset_budget()
    cur = conn.execute(template.sql, bind)
    columns = tuple(d[0] for d in cur.description)
    fetched = cur.fetchmany(req.limit + 1)
    rows = [dict(zip(columns, r)) for r in fetched[:req.limit]]
    return QueryResult(columns, rows, len(fetched) > req.limit)


def redact_row(row: dict, pii: dict[str, str] = PII_COLUMNS) -> tuple[dict, int]:
    """A copy of `row` with every non-None value in a PII column replaced by its marker,
    and the number of values replaced. The input row is not modified."""
    out, n = {}, 0
    for key, value in row.items():
        if key in pii and value is not None:
            out[key] = pii[key]
            n += 1
        else:
            out[key] = value
    return out, n


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
    problems = []
    for name, t in templates.items():
        sql = t.sql
        if not sql.lstrip().upper().startswith("SELECT") or ";" in sql:
            problems.append(f"{name}: not a single SELECT")
        if "*" in sql:
            problems.append(f"{name}: selects *")
        if "{" in sql or "%s" in sql or "?" in sql:
            problems.append(f"{name}: string formatting")
        used = set(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", sql))
        problems += [f"{name}: undeclared parameter :{p}" for p in sorted(used - set(t.params))]
        problems += [f"{name}: unused parameter {p}" for p in t.params if p not in used]
        for table in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE):
            if table not in allowed_tables:
                problems.append(f"{name}: table not allowlisted: {table}")
        words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sql))
        problems += [f"{name}: secret column: {c}" for c in sorted(set(secret_columns) & words)]
    return problems


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
    raw = canonical(request)
    entry = {"caller": caller, "request_sha256": hashlib.sha256(raw).hexdigest(), "request_bytes": len(raw),
             "template": None, "params": None, "limit": None, "rows": 0, "truncated": False, "redacted_values": 0}
    try:
        req = validate_request(request, templates)
        entry.update(template=req.template, params=req.params, limit=req.limit)
        result = run_template(conn, req, templates)
        rows, redacted = [], 0
        for row in result.rows:
            clean, n = redact_row(row)
            rows.append(clean)
            redacted += n
        response = {"ok": True, "template": req.template, "columns": list(result.columns), "rows": rows,
                    "row_count": len(rows), "truncated": result.truncated, "redacted_values": redacted}
        entry.update(outcome="ok", rows=len(rows), truncated=result.truncated, redacted_values=redacted)
    except PolicyError as exc:
        response = {"ok": False, "error": exc.code, "message": exc.message}
        entry["outcome"] = exc.code
    except sqlite3.Error:
        response = {"ok": False, "error": "query_failed", "message": "the query could not be completed"}
        entry["outcome"] = "query_failed"
    try:
        audit.record(**entry)
    except Exception:
        return {"ok": False, "error": "audit_failed", "message": "the call could not be audited"}
    return response

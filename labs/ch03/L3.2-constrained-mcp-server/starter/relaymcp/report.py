"""Replay the request set through the policy and report what happened (provided).

    python -m relaymcp.report --data ../data
    python -m relaymcp.report --data ../data --show A07     # one request in detail

The report also checks the responses for leaks against an unrestricted copy
of the database: no response may contain any user's email address, display
name, password hash or token hash, and no table may change.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from . import policy
from .db import open_readonly
from .templates import MAX_LIMIT, MAX_REQUEST_BYTES, TEMPLATES

FIXED_CLOCK = "2026-11-08T09:00:00+00:00"


def load_requests(data: Path) -> list[dict]:
    return [json.loads(line) for line in (data / "requests.jsonl").read_text(encoding="utf-8").splitlines() if line]


def sensitive_values(data: Path) -> tuple[set[str], dict[str, int]]:
    """Every email, name and hash in the database, and each table's row count, read without the policy."""
    raw = sqlite3.connect(":memory:")
    raw.executescript((data / "relay-test.sql").read_text(encoding="utf-8"))
    values = set()
    for email, name, pw, tok in raw.execute("SELECT email, display_name, password_hash, api_token_hash FROM users"):
        values.update(v for v in (email, name, pw, tok) if v)
    tables = [r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    counts = {t: raw.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}  # noqa: S608 (trusted names)
    return values, counts


def run(data: Path) -> tuple[list[tuple[dict, dict]], policy.AuditLog, sqlite3.Connection]:
    conn = open_readonly(data / "relay-test.sql")
    audit = policy.AuditLog(clock=lambda: FIXED_CLOCK)
    results = [(r, policy.handle(r["request"], conn, audit, caller="report")) for r in load_requests(data)]
    return results, audit, conn


def leaks(results: list[tuple[dict, dict]], values: set[str]) -> int:
    return sum(any(v in json.dumps(resp) for v in values) for _, resp in results)


def table_counts(conn: sqlite3.Connection, names: list[str]) -> dict[str, int]:
    out = {}
    for t in names:
        conn.reset_budget()
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608 (trusted names)
    return out


def render(data: Path) -> str:
    results, audit, conn = run(data)
    values, before_counts = sensitive_values(data)
    lines = ["# Constrained MCP query tool: request replay", "",
             f"Templates: {len(TEMPLATES)} · row cap {MAX_LIMIT} · request cap {MAX_REQUEST_BYTES} bytes", "",
             "| Request | Kind | Intent | Outcome | Rows | Truncated | Redacted values |",
             "| --- | --- | --- | --- | ---: | --- | ---: |"]
    for r, resp in results:
        outcome = "ok" if resp["ok"] else resp["error"]
        rows = resp.get("row_count", 0)
        lines.append(f"| {r['id']} | {r['kind']} | {r['intent']} | {outcome} | {rows} | "
                     f"{'yes' if resp.get('truncated') else ''} | {resp.get('redacted_values', 0)} |")
    by_kind = Counter(r["kind"] for r, _ in results)
    refused = Counter(resp["error"] for _, resp in results if not resp["ok"])
    attacks_ok = [r["id"] for r, resp in results if r["kind"] == "attack" and resp["ok"]]
    lines += ["", "| Summary | Value |", "| --- | ---: |",
              f"| Requests | {len(results)} |",
              f"| Legitimate, answered | {sum(resp['ok'] for r, resp in results if r['kind'] == 'legitimate')} of {by_kind['legitimate']} |",
              f"| Attacks refused | {sum(not resp['ok'] for r, resp in results if r['kind'] == 'attack')} of {by_kind['attack']} |",
              f"| Attacks answered harmlessly (bound as data) | {len(attacks_ok)} ({', '.join(attacks_ok)}) |",
              f"| Rows returned, total | {sum(resp.get('row_count', 0) for _, resp in results)} |",
              f"| Values redacted | {sum(resp.get('redacted_values', 0) for _, resp in results)} |",
              f"| Audit entries | {len(audit.entries)} |",
              f"| Responses containing an email, name or hash from the database | {leaks(results, values)} |"]
    after = table_counts(conn, [t for t in before_counts if t != "workspaces"])
    unchanged = all(after[t] == before_counts[t] for t in after)
    lines.append(f"| Tables unchanged after the run | {'yes' if unchanged else 'NO'} ({after['tasks']} tasks) |")
    lines += ["", "| Refusals by code | Count |", "| --- | ---: |"]
    lines += [f"| {code} | {n} |" for code, n in sorted(refused.items())]
    problems = policy.lint_templates()
    lines += ["", f"Template lint: {len(problems)} problem(s)"] + [f"- {p}" for p in problems]
    return "\n".join(lines)


def show(data: Path, rid: str) -> str:
    request = {r["id"]: r for r in load_requests(data)}[rid]
    conn = open_readonly(data / "relay-test.sql")
    audit = policy.AuditLog(clock=lambda: FIXED_CLOCK)
    response = policy.handle(request["request"], conn, audit, caller="report")
    raw = request["request"]
    lines = [f"Request {rid} ({request['kind']}): {request['intent']}",
             f"Raw ({len(policy.canonical(raw))} bytes): {raw if len(raw) <= 160 else raw[:160] + '…'}"]
    try:
        req = policy.validate_request(raw)
        t = TEMPLATES[req.template]
        bound = {n: ("%" + policy.escape_like(v) + "%" if t.params[n].like and v is not None else v)
                 for n, v in req.params.items()}
        lines += [f"SQL: {t.sql}", f"Bound parameters: {json.dumps(bound)}", f"Limit: {req.limit}"]
    except policy.PolicyError as exc:
        lines.append(f"Refused before any SQL ran: {exc.code} ({exc.message})")
    lines += [f"Response: {json.dumps(response)}", f"Audit entry: {json.dumps(audit.entries[-1], sort_keys=True)}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay requests through the constrained query policy")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--show", help="print one request in detail, e.g. A07")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(show(args.data, args.show) if args.show else render(args.data))


if __name__ == "__main__":
    main()

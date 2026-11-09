"""Runtime fitness checks: architecture properties measured on the running system (added in 4.27.0; ADR-037).

Chapter 6's fitness functions read the source. Some properties exist only at run time, and Chapter 6 left
them to observability. Each check here returns a `Check` with a pass or fail, the measured value and the
evidence, and runs on a schedule like any other alert source.

- RF-001 (ESC-AC30): at least 95% of escalation steps in a week fired within 60 seconds of their due time.
- RF-002 (ESC-AC29): the newest completed worker pass is at most 300 seconds old.
- RF-003 (ADR-023, ADR-036): exported telemetry holds no key outside the allowlist, no content key and
  nothing the redactor would still replace.
- RF-004 (ADR-036): no metric instrument has folded attribute sets into its overflow series.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from ..escalation import evaluate, rule_from_document
from . import semconv
from .redact import leaks

_ESC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(frozen=True)
class Check:
    check_id: str
    title: str
    passed: bool
    value: float
    threshold: float
    detail: str


def step_delay_check(delays_s: list[float], within_s: float = 60.0, share: float = 0.95) -> Check:
    """RF-001 over (fired - due) delays in seconds. No steps in the week is a pass with a note."""
    if not delays_s:
        return Check("RF-001", "Escalation steps fire on time (ESC-AC30)", True, 1.0, share, "no steps this week")
    on_time = sum(1 for d in delays_s if d <= within_s)
    ratio = on_time / len(delays_s)
    return Check("RF-001", "Escalation steps fire on time (ESC-AC30)", ratio >= share, round(ratio, 4), share,
                 f"{on_time} of {len(delays_s)} steps within {within_s:g} s; worst {max(delays_s):.1f} s")


def escalation_step_delays(store, tasks, task_ids, since: datetime, until: datetime) -> list[float]:
    """Delays of steps fired in [since, until), from the task's activity and its rule's due times.

    Uses `relay.escalation`'s public interface only. The due time is recomputed by `evaluate` at the fired
    time with no steps fired and no acknowledgement, which is how the pass saw the task then. Limit: a
    priority changed after the step fired moves the recomputed due time; such steps are skipped.
    """
    delays = []
    for task_id in task_ids:
        task = tasks.get(task_id)
        if task is None:
            continue
        state = replace(store.state(task_id), fired_steps=frozenset(), acknowledged_at=None)
        for item in store.activity(task_id):
            if item["kind"] != "escalated":
                continue
            fired = datetime.strptime(item["at"], _ESC_FORMAT).replace(tzinfo=timezone.utc)
            if not since <= fired < until:
                continue
            document = store.rule_document(item["rule_id"], include_deleted=True)
            if document is None:
                continue
            decision = [d for d in evaluate(rule_from_document(document), task, state, fired).fire
                        if d.step == item["step"]]
            if decision:
                delays.append((fired - decision[0].due_at).total_seconds())
    return delays


def heartbeat_check(age_s: float | None, limit_s: float = 300.0) -> Check:
    if age_s is None:
        return Check("RF-002", "Worker heartbeat is fresh (ESC-AC29)", False, float("inf"), limit_s, "no pass yet")
    return Check("RF-002", "Worker heartbeat is fresh (ESC-AC29)", age_s <= limit_s, age_s, limit_s,
                 f"newest pass {age_s:g} s ago")


def _walk(node, keys: set, strings: list) -> None:
    """Attribute keys and every string value (attributes, log bodies, status messages) in an OTLP request."""
    if isinstance(node, dict):
        if "key" in node and "value" in node and isinstance(node["key"], str):
            keys.add(node["key"])
        for k, v in node.items():
            if k in ("stringValue", "message", "name") and isinstance(v, str):
                strings.append(v)
            else:
                _walk(v, keys, strings)
    elif isinstance(node, list):
        for v in node:
            _walk(v, keys, strings)


def telemetry_leak_check(paths: list[str | Path]) -> Check:
    """RF-003 over OTLP JSON-lines files: keys outside the allowlist, content keys, and redactable values."""
    keys: set = set()
    findings = 0
    lines = 0
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            lines += 1
            strings: list = []
            _walk(json.loads(line), keys, strings)
            findings += sum(sum(leaks(v).values()) for v in strings)
    bad_keys = sorted(k for k in keys if k not in semconv.ALLOWED or k in semconv.CONTENT_KEYS)
    total = findings + len(bad_keys)
    detail = f"{lines} export line(s); {findings} redactable value(s); keys outside the allowlist: {bad_keys or 'none'}"
    return Check("RF-003", "Telemetry holds no personal data or content", total == 0, total, 0, detail)


def cardinality_check(meter) -> Check:
    over = meter.overflow_report()
    detail = ", ".join(f"{k}: {v}" for k, v in over.items()) or "no instrument overflowed"
    return Check("RF-004", "Metric cardinality stays under each instrument's limit", not over,
                 sum(over.values()), 0, detail)


def held_p1_unacknowledged(store, task_ids, now: datetime, after_s: float = 600.0) -> int:
    """AL-006's value: P1 steps held by the flood cap, on tasks still unacknowledged `after_s` after the hold.

    Read from each task's activity (`not_emailed` with reason `flood_cap`) and its rule's priority, through
    `relay.escalation`'s public interface (D7 pilot review, `docs/slo/d7-pilot-review.md`).
    """
    count = 0
    for task_id in task_ids:
        state = store.state(task_id)
        for item in store.activity(task_id):
            if item["kind"] != "not_emailed" or item.get("reason") != "flood_cap":
                continue
            document = store.rule_document(item["rule_id"], include_deleted=True)
            if document is None or document.get("priority") != "P1":
                continue
            held = datetime.strptime(item["at"], _ESC_FORMAT).replace(tzinfo=timezone.utc)
            acked = state.acknowledged_at
            late = acked is None or (acked - held).total_seconds() > after_s
            if (now - held).total_seconds() > after_s and late:
                count += 1
    return count

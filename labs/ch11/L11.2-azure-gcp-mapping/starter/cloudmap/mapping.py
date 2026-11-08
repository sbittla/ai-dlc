"""A structured service mapping, and a checker that keeps it honest.

A mapping row says which service does a job on each provider, how close the equivalents are, and
what differs. "Close" with no differences is the claim that most often turns out false, so the
checker insists that every non-close row names its differences, and that every dimension of
difference (identity, networking, quotas, pricing, guardrails, data) appears somewhere.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PROVIDERS = ("aws", "azure", "gcp")
EQUIVALENCE = ("close", "partial", "different")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def differences_by_dimension(mapping: dict) -> dict[str, int]:
    """Provided: how many difference notes the mapping has per dimension."""
    counts = Counter(d["dimension"] for r in mapping["rows"] for d in r["differences"])
    return {dim: counts.get(dim, 0) for dim in mapping["dimensions"]}


def check_mapping(mapping: dict, required: list[str]) -> list[str]:
    """TODO 1. Return every problem found, as strings, in this order; [] means the mapping passes.

    1. Each concern in `required` that has no row: "missing concern: <concern>".
    2. Each concern with more than one row, once: "duplicate concern: <concern>".
    3. For each row, in order, with <c> its concern:
       - a provider in PROVIDERS whose name is empty: "<c>: no <provider> service"
       - equivalence not in EQUIVALENCE: "<c>: unknown equivalence '<value>'"
       - equivalence "partial" or "different" with no differences: "<c>: <equivalence> but no difference given"
       - each difference whose dimension is not in mapping["dimensions"]:
         "<c>: unknown dimension '<dimension>'"
       - verify not true: "<c>: not marked for verification"
    4. Each dimension in mapping["dimensions"] with no difference anywhere, in that order:
       "no difference recorded for <dimension>".
    """
    raise NotImplementedError("TODO 1: check_mapping")

"""Run every design on every task of a split, three times each, and summarize (provided).

Outcomes are judged as Lab 7.1 judged triage: against expected results the designs never see.
- A local or cross_file task succeeds if a pull request was opened and its change is correct by the hidden
  acceptance tests. A pull request whose change is a `hack` passes the approved tests only: a wrong PR.
- An out_of_scope task succeeds if the run handed the task back and opened no pull request. A run stopped
  by its budget has not handed anything back on purpose, so it fails.
"""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache

from relay.agents import AgentRevoked, Budget, BudgetExceeded

from . import DATA_DIR
from .designs import DESIGN_FUNCTIONS
from .runtime import RunRecord, Runtime, load_json
from .stats import percentile, wilson_interval
from .world import load_tasks

DESIGNS = ("workflow", "single", "multi", "routed")
LABELS = {"workflow": "Workflow", "single": "Single agent", "multi": "Multi-agent", "routed": "Routed"}


def config() -> tuple[dict, dict, dict]:
    return (load_json(DATA_DIR / "simulator.json"), load_json(DATA_DIR / "designs.json"),
            load_json(DATA_DIR / "registry.json"))


def tasks(split: str | None = None):
    all_tasks = load_tasks(DATA_DIR / "tasks.jsonl")
    return [t for t in all_tasks if split is None or t.split == split]


def run_design(task, run: int, design: str, cfg: dict, designs: dict, registry: dict,
               budget: dict | None = None) -> RunRecord:
    spec = designs["designs"][design]
    rt = Runtime(task, run, design, cfg, Budget(**(budget or spec["budget"])), registry)
    try:
        status, reason = DESIGN_FUNCTIONS[design](rt, spec)
    except BudgetExceeded as exc:
        status, reason = "stopped", f"budget:{exc.kind}"
    except AgentRevoked as exc:
        status, reason = exc.status, exc.code
    return rt.record(status, reason)


@lru_cache(maxsize=8)
def evaluate(split: str, calibration: bool = False) -> tuple[RunRecord, ...]:
    cfg, designs, registry = config()
    budget = designs["calibration_budget"] if calibration else None
    out = []
    for task in tasks(split):
        for run in range(1, designs["repeats"] + 1):
            for design in DESIGNS:
                out.append(run_design(task, run, design, cfg, designs, registry, budget))
    return tuple(out)


def by_design(records, design: str) -> list[RunRecord]:
    return [r for r in records if r.design == design]


def majority(records: list[RunRecord]) -> dict[str, bool]:
    """Each task's majority outcome over its runs (2 of 3)."""
    runs: dict[str, list[bool]] = {}
    for r in records:
        runs.setdefault(r.task_id, []).append(r.success)
    return {t: sum(v) * 2 > len(v) for t, v in runs.items()}


def summarize(records: list[RunRecord]) -> dict:
    n_runs = len(records)
    maj = majority(records)
    k, n = sum(maj.values()), len(maj)
    lo, hi = wilson_interval(k, n)
    successes = sum(r.success for r in records)
    usd = sum(r.usd for r in records)
    return {
        "tasks": n, "tasks_succeeded": k, "rate": k / n, "low": lo, "high": hi,
        "run_rate": successes / n_runs,
        "usd_per_run": usd / n_runs, "usd_per_success": usd / successes if successes else float("inf"),
        "median_s": percentile([r.seconds for r in records], 0.5),
        "p90_s": percentile([r.seconds for r in records], 0.9),
        "model_calls": sum(r.model_calls for r in records) / n_runs,
        "tool_calls": sum(r.tool_calls for r in records) / n_runs,
        "wrong_prs": sum(r.wrong_pr for r in records),
        "budget_stops": sum(r.status == "stopped" for r in records),
        "hand_backs": sum(r.status == "handed_back" for r in records),
        "runs": n_runs,
    }


def record_dicts(records) -> list[dict]:
    return [asdict(r) for r in records]


@lru_cache(maxsize=2)
def routed_without_review(split: str) -> tuple[RunRecord, ...]:
    """The routed design as first built, before its review step was added on the evidence of the dev split."""
    cfg, designs, registry = config()
    designs = {**designs, "designs": {**designs["designs"],
                                      "routed": {**designs["designs"]["routed"], "review": False}}}
    return tuple(run_design(t, run, "routed", cfg, designs, registry) for t in tasks(split)
                 for run in range(1, designs["repeats"] + 1))

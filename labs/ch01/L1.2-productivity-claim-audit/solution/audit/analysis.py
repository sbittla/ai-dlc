"""Audit a vendor productivity claim (reference solution).

The vendor's headline: "developers using Tachyon Agents finished tasks 38%
faster". Each function below answers one question an auditor should ask
before believing a number like that.
"""

from __future__ import annotations

import csv
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

SIZES = ("S", "M", "L")
ARMS = ("control", "ai")


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    developer_id: str
    arm: str  # "control" or "ai"
    task_size: str  # "S", "M" or "L"
    minutes: float
    passed_review: bool
    defects_30d: int


def load(path: Path) -> list[Attempt]:
    with path.open(encoding="utf-8") as f:
        return [
            Attempt(
                attempt_id=r["attempt_id"],
                developer_id=r["developer_id"],
                arm=r["arm"],
                task_size=r["task_size"],
                minutes=float(r["minutes"]),
                passed_review=r["passed_review"] == "true",
                defects_30d=int(r["defects_30d"]),
            )
            for r in csv.DictReader(f)
        ]


def _arm(rows: list[Attempt], arm: str, size: str | None = None) -> list[Attempt]:
    return [r for r in rows if r.arm == arm and (size is None or r.task_size == size)]


def naive_speedup(rows: list[Attempt]) -> float:
    """The vendor's number: 1 - mean(AI minutes) / mean(control minutes), all tasks pooled."""
    ai = statistics.mean(r.minutes for r in _arm(rows, "ai"))
    ctrl = statistics.mean(r.minutes for r in _arm(rows, "control"))
    return 1 - ai / ctrl


def task_mix(rows: list[Attempt], arm: str) -> dict[str, float]:
    """Share of each task size within one arm. Reveals selection bias."""
    arm_rows = _arm(rows, arm)
    return {s: sum(r.task_size == s for r in arm_rows) / len(arm_rows) for s in SIZES}


def speedup_by_size(rows: list[Attempt]) -> dict[str, float]:
    """1 - mean(AI) / mean(control), computed separately for each task size."""
    out = {}
    for s in SIZES:
        ai = statistics.mean(r.minutes for r in _arm(rows, "ai", s))
        ctrl = statistics.mean(r.minutes for r in _arm(rows, "control", s))
        out[s] = 1 - ai / ctrl
    return out


def reweighted_speedup(rows: list[Attempt], mix: dict[str, float]) -> float:
    """Speedup if both arms worked on the same task mix (`mix`, shares summing to 1).

    This is direct standardization: compute each arm's mean minutes per task
    size, weight both by the *same* mix, then compare. Use your own team's
    backlog mix, not the vendor's.
    """
    if abs(sum(mix.values()) - 1) > 1e-9:
        raise ValueError("mix shares must sum to 1")

    def weighted(arm: str) -> float:
        return sum(mix[s] * statistics.mean(r.minutes for r in _arm(rows, arm, s)) for s in SIZES)

    return 1 - weighted("ai") / weighted("control")


def bootstrap_ci(rows: list[Attempt], mix: dict[str, float], n_resamples: int = 2000,
                 seed: int = 7, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for `reweighted_speedup`.

    Algorithm (follow it exactly to reproduce the reference numbers):
    1. rng = random.Random(seed).
    2. Build cells in the order arm in ("control", "ai"), then size in
       ("S", "M", "L"); each cell keeps the original row order.
    3. For each of n_resamples: for each cell in that order, draw len(cell)
       rows with rng.choice(cell); compute reweighted_speedup on the result.
    4. Sort the estimates; return the values at indexes
       int((1 - level) / 2 * n) and int((1 + level) / 2 * n) - 1.

    Resampling within cells keeps each arm's task mix fixed, so the interval
    reflects noise within task sizes, not a different mix. It treats attempts
    as independent; attempts by the same developer are not, so the interval
    is somewhat too narrow (a cluster bootstrap by developer would widen it).
    """
    rng = random.Random(seed)
    cells = {(a, s): _arm(rows, a, s) for a in ARMS for s in SIZES}
    estimates = []
    for _ in range(n_resamples):
        resample = [rng.choice(cell) for cell in cells.values() for _ in cell]
        estimates.append(reweighted_speedup(resample, mix))
    estimates.sort()
    lo_idx = int((1 - level) / 2 * n_resamples)
    hi_idx = int((1 + level) / 2 * n_resamples) - 1
    return estimates[lo_idx], estimates[hi_idx]


def acceptance_rate(rows: list[Attempt], arm: str, mix: dict[str, float] | None = None) -> float:
    """Share of attempts that passed review. With `mix`, standardized to that task mix."""
    if mix is None:
        arm_rows = _arm(rows, arm)
        return sum(r.passed_review for r in arm_rows) / len(arm_rows)
    return sum(mix[s] * acceptance_rate(_arm(rows, arm, s), arm) for s in SIZES)


def defects_per_attempt(rows: list[Attempt], arm: str, mix: dict[str, float] | None = None) -> float:
    """Mean defects found within 30 days per attempt; standardized to `mix` if given, raw otherwise."""
    if mix is None:
        return statistics.mean(r.defects_30d for r in _arm(rows, arm))
    return sum(mix[s] * statistics.mean(r.defects_30d for r in _arm(rows, arm, s)) for s in SIZES)


def minutes_per_accepted_task(rows: list[Attempt], arm: str, mix: dict[str, float]) -> float:
    """Quality-adjusted cost: standardized mean minutes divided by standardized acceptance rate.

    A rejected attempt still cost time, so the real cost of one accepted task
    is higher than the raw time of one attempt.
    """
    minutes = sum(mix[s] * statistics.mean(r.minutes for r in _arm(rows, arm, s)) for s in SIZES)
    return minutes / acceptance_rate(rows, arm, mix)


@dataclass(frozen=True)
class AuditResult:
    naive_speedup: float
    mix_control: dict[str, float]
    mix_ai: dict[str, float]
    speedup_by_size: dict[str, float]
    reweighted_speedup: float
    ci: tuple[float, float]
    acceptance_control: float
    acceptance_ai: float
    defects_control: float
    defects_ai: float
    defects_control_raw: float
    defects_ai_raw: float
    quality_adjusted_speedup: float


def audit(rows: list[Attempt], team_mix: dict[str, float]) -> AuditResult:
    mpa_ctrl = minutes_per_accepted_task(rows, "control", team_mix)
    mpa_ai = minutes_per_accepted_task(rows, "ai", team_mix)
    return AuditResult(
        naive_speedup=naive_speedup(rows),
        mix_control=task_mix(rows, "control"),
        mix_ai=task_mix(rows, "ai"),
        speedup_by_size=speedup_by_size(rows),
        reweighted_speedup=reweighted_speedup(rows, team_mix),
        ci=bootstrap_ci(rows, team_mix),
        acceptance_control=acceptance_rate(rows, "control", team_mix),
        acceptance_ai=acceptance_rate(rows, "ai", team_mix),
        defects_control=defects_per_attempt(rows, "control", team_mix),
        defects_ai=defects_per_attempt(rows, "ai", team_mix),
        defects_control_raw=defects_per_attempt(rows, "control"),
        defects_ai_raw=defects_per_attempt(rows, "ai"),
        quality_adjusted_speedup=1 - mpa_ai / mpa_ctrl,
    )

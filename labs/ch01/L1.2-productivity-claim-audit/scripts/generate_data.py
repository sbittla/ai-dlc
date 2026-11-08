"""Generate the synthetic vendor trial dataset used in Lab 1.2.

A fictional vendor ("Tachyon Agents") ran a trial and claims its coding agent
makes developers "38% faster". The raw trial data is in data/trial.csv.

The generator encodes three realistic flaws that the audit must find:

1. Selection bias: developers in the AI arm chose their own tasks and picked
   far more small tasks than the control arm.
2. Heterogeneous effects: the agent helps on small tasks, helps a little on
   medium tasks and slows developers down on large ones.
3. Quality cost: AI-arm changes fail review more often and produce more
   defects within 30 days, which the headline number ignores.

Deterministic (fixed seed). Re-run with:  python scripts/generate_data.py
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path

SEED = 20260214
N_PER_ARM = 150

BASE_MINUTES = {"S": 60, "M": 180, "L": 480}
MIX = {"control": {"S": 0.30, "M": 0.40, "L": 0.30}, "ai": {"S": 0.60, "M": 0.30, "L": 0.10}}
TIME_MULTIPLIER = {"S": 0.75, "M": 0.90, "L": 1.10}  # true effect of the agent on time
PASS_REVIEW = {"control": {"S": 0.92, "M": 0.90, "L": 0.88}, "ai": {"S": 0.88, "M": 0.80, "L": 0.65}}
DEFECT_MEAN = {"control": {"S": 0.20, "M": 0.40, "L": 0.80}, "ai": {"S": 0.25, "M": 0.60, "L": 1.30}}


def poisson(rng: random.Random, lam: float) -> int:
    """Knuth's algorithm; fine for the small means used here."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def sample_size(rng: random.Random, mix: dict[str, float]) -> str:
    r, acc = rng.random(), 0.0
    for size, share in mix.items():
        acc += share
        if r < acc:
            return size
    return "L"


def generate(out: Path) -> None:
    rng = random.Random(SEED)
    rows = []
    attempt = 0
    for arm in ("control", "ai"):
        for _ in range(N_PER_ARM):
            attempt += 1
            size = sample_size(rng, MIX[arm])
            multiplier = TIME_MULTIPLIER[size] if arm == "ai" else 1.0
            minutes = BASE_MINUTES[size] * multiplier * math.exp(rng.gauss(0, 0.35))
            rows.append({
                "attempt_id": f"T{attempt:03d}",
                "developer_id": f"dev{rng.randint(1, 24):02d}",
                "arm": arm,
                "task_size": size,
                "minutes": round(minutes, 1),
                "passed_review": str(rng.random() < PASS_REVIEW[arm][size]).lower(),
                "defects_30d": poisson(rng, DEFECT_MEAN[arm][size]),
            })
    rng.shuffle(rows)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "trial.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} trial attempts to {out / 'trial.csv'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    generate(parser.parse_args().out)

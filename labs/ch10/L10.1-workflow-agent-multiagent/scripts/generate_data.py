"""Write Lab 10.1's generated data (deterministic; run from anywhere).

    python scripts/generate_data.py

Writes data/tasks.jsonl: 120 spec-to-PR tasks in 40 families of three. A family is one spec change;
its three tasks share their files, their shape and their approved test file, and differ in difficulty.
Families F01-F10 are the dev split (30 tasks), F11-F40 the held-out split (90 tasks).

File sizes are those of canonical Relay 4.23.0's modules (labs/relay-baselines/4.23.0/relay-repo/src) at
four characters per token, so the context each design reads has the size of Relay's real code. Shapes
are assigned from a fixed mix per split and shuffled with a fixed seed; nothing is drawn from a model.

The other inputs (simulator.json, designs.json, registry.json, incident/pipeline.json) are written by
hand and documented in the README.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
RELAY = LAB.parent.parent / "relay-baselines" / "4.23.0" / "relay-repo" / "src"
SEED = 1010
TEST_TOKENS = 1800  # each family's approved test file, written for the task

POOL = [
    "src/relay/escalation/engine.py", "src/relay/escalation/store.py", "src/relay/escalation/rules.py",
    "src/relay/escalation/hours.py", "src/relay/escalation/delivery.py", "src/relay/escalation/model.py",
    "src/relay/escalation/contract.py", "src/relay/escalation/migrations.py", "src/relay/escalation/evaluate.py",
    "src/relay/notify/decide.py", "src/relay/notify/store.py", "src/relay/notify/migrate.py",
    "src/relay/service/app.py", "src/relay/service/escalation_routes.py", "src/relay/service/responses.py",
    "src/relay/service/directory.py", "src/relay/service/ratelimit.py", "src/relay/worker/queue.py",
    "src/relay/worker/runner.py", "src/relay/worker/triage.py", "src/relay/worker/escalation.py",
    "src/relay/store.py", "src/relay/roles.py", "src/relay/api.py", "src/relay/duedates.py",
]
TITLES = ["Validate a new rule field", "Add a refusal code", "Count a new outcome", "Expose a field in a view",
          "Bound a list endpoint", "Record a new audit outcome", "Handle an empty input", "Add a filter",
          "Rename an internal helper", "Tighten a boundary check"]
MIX = {"dev": ["local"] * 6 + ["cross_file"] * 3 + ["out_of_scope"],
       "heldout": ["local"] * 18 + ["cross_file"] * 7 + ["out_of_scope"] * 5}


def tokens(path: str) -> int:
    return len((RELAY.parent / path).read_text(encoding="utf-8")) // 4


def main() -> None:
    rng = random.Random(SEED)
    shapes = []
    for split in ("dev", "heldout"):
        mix = list(MIX[split])
        rng.shuffle(mix)
        shapes += [(split, s) for s in mix]
    rows = []
    for f, (split, shape) in enumerate(shapes, 1):
        family = f"F{f:02d}"
        picked = rng.sample(POOL, 4)
        n_files = 1 + (f % 2)
        files = sorted(picked[:n_files])
        extra = picked[n_files]
        by_import = shape != "local" and rng.random() < 0.5
        for i, difficulty in enumerate(("easy", "easy", "hard") if f % 3 else ("easy", "hard", "hard")):
            n = (f - 1) * 3 + i + 1
            sizes = {p: tokens(p) for p in files + [extra]}
            sizes[f"tests/test_{family.lower()}.py"] = TEST_TOKENS
            rows.append({
                "task_id": f"HT-{n:03d}", "family": family, "split": split, "shape": shape,
                "difficulty": difficulty, "title": TITLES[(f + i) % len(TITLES)], "files": files,
                "tests": f"tests/test_{family.lower()}.py", "test_count": 3 + (n % 4),
                "symbol": f"sym_{family.lower()}",
                "context_file": extra if shape == "cross_file" else None,
                "context_by_import": by_import,
                "outside_file": extra if shape == "out_of_scope" else None,
                "tokens": sizes,
            })
    out = LAB / "data" / "tasks.jsonl"
    out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} tasks to {out}")


if __name__ == "__main__":
    main()

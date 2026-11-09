"""Extract per-run token usage from Lab 10.1's reference solution into data/source/ch10-runs.jsonl.

    python scripts/extract_ch10.py [--out FILE]   # needs labs/ch10/L10.1-workflow-agent-multiagent alongside

Lab 10.1 records each run's cost but not its token split. This script runs Lab 10.1's own evaluation (the dev
split under its calibration budget, and the held-out split under each design's budget) and records, per run,
the meter's input, cached and output tokens as well. It changes nothing in Lab 10.1. generate_data.py does not
run it; the extracted file is committed, and tests/test_data.py re-runs this extraction when Lab 10.1 is present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
L101 = LAB.parent.parent / "ch10" / "L10.1-workflow-agent-multiagent" / "solution"
OUT = LAB / "data" / "source" / "ch10-runs.jsonl"


def extract() -> list[dict]:
    sys.path.insert(0, str(L101))
    from agentlab import runtime
    from agentlab import evaluate as ev

    tokens: dict[int, tuple[int, int, int]] = {}
    original = runtime.Runtime.record

    def record(self, status, reason):
        rec = original(self, status, reason)
        tokens[id(rec)] = (self.meter.input_tokens, self.meter.cached_tokens, self.meter.output_tokens)
        return rec

    runtime.Runtime.record = record
    try:
        rows = []
        for split, calibration in (("dev", True), ("heldout", False)):
            for r in ev.evaluate(split, calibration):
                i, c, o = tokens[id(r)]
                rows.append({"split": split, "calibration": calibration, "design": r.design, "task_id": r.task_id,
                             "run": r.run, "status": r.status, "success": r.success, "escalated": r.escalated,
                             "usd": r.usd, "input_tokens": i, "cached_tokens": c, "output_tokens": o})
        return rows
    finally:
        runtime.Runtime.record = original


def text(rows: list[dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)


def main() -> None:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text(extract()).encode("utf-8"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

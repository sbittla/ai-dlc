"""Print the audit findings as Markdown.

Usage (from starter/ or solution/):

    python -m audit.report --data ../data/trial.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import analysis

# Relay's next-quarter backlog, by estimated effort (S: about an hour,
# M: about half a day, L: a day or more). Supplied by Relay's product owner
# in the lab brief. Override with --mix to test how sensitive the result is.
RELAY_MIX = {"S": 0.25, "M": 0.45, "L": 0.30}


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def render(r: analysis.AuditResult, mix: dict[str, float]) -> str:
    mix_txt = ", ".join(f"{s} {v:.0%}" for s, v in mix.items())
    lines = [
        "| Question | Finding |",
        "| --- | --- |",
        f"| Vendor headline (pooled means) | {pct(r.naive_speedup)} faster |",
        "| Task mix, control arm | " + ", ".join(f"{s} {v:.0%}" for s, v in r.mix_control.items()) + " |",
        "| Task mix, AI arm | " + ", ".join(f"{s} {v:.0%}" for s, v in r.mix_ai.items()) + " |",
        "| Speedup by task size | " + ", ".join(f"{s} {pct(v)}" for s, v in r.speedup_by_size.items()) + " |",
        f"| Speedup on our mix ({mix_txt}) | {pct(r.reweighted_speedup)} |",
        f"| 95% bootstrap interval | {pct(r.ci[0])} to {pct(r.ci[1])} |",
        f"| Review pass rate on our mix, control vs AI | {r.acceptance_control:.0%} vs {r.acceptance_ai:.0%} |",
        f"| Defects per attempt within 30 days, raw, control vs AI | {r.defects_control_raw:.2f} vs {r.defects_ai_raw:.2f} |",
        f"| Defects per attempt within 30 days, on our mix, control vs AI | {r.defects_control:.2f} vs {r.defects_ai:.2f} |",
        f"| Speedup per *accepted* task on our mix | {pct(r.quality_adjusted_speedup)} |",
    ]
    return "\n".join(lines)


def parse_mix(text: str) -> dict[str, float]:
    parts = dict(p.split("=") for p in text.split(","))
    return {s: float(parts[s]) for s in analysis.SIZES}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the vendor productivity claim")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--mix", type=parse_mix, default=RELAY_MIX, help="e.g. S=0.25,M=0.45,L=0.30")
    args = parser.parse_args()
    rows = analysis.load(args.data)
    print(render(analysis.audit(rows, args.mix), args.mix))


if __name__ == "__main__":
    main()

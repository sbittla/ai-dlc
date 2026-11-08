"""Score the rule-based detector (and optionally a live model) per defect type and split.

Offline (default, free, deterministic):
    python -m ambeval.report --data ../data/statements.jsonl \\
        --lexicon ../data/lexicon-v1.json --lexicon ../data/lexicon-v2.json

    --errors SPLIT   list every miss and false alarm on that split, for the last lexicon
Live (costs money; needs `pip install -e ".[live]"` and credentials):
    python -m ambeval.report --data ../data/statements.jsonl --lexicon ../data/lexicon-v1.json \\
        --live claude-haiku-5-5 --split heldout --max-usd 1.00
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import detector, scoring
from .data import DEFECTS, SPLITS, load_lexicon, load_statements


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def ci(x: tuple[float, float] | None) -> str:
    return "" if x is None else f" ({x[0]:.0%}–{x[1]:.0%})"


def dataset_table(statements) -> str:
    lines = ["| Split | Statements | Sets | Clean | " + " | ".join(DEFECTS) + " |",
             "| --- | ---: | ---: | ---: | " + " | ".join("---:" for _ in DEFECTS) + " |"]
    for split in SPLITS:
        ss = [s for s in statements if s.split == split]
        counts = Counter(d for s in ss for d in s.defects)
        lines.append(f"| {split} | {len(ss)} | {len({s.set for s in ss})} | {sum(not s.defects for s in ss)} | "
                     + " | ".join(str(counts[d]) for d in DEFECTS) + " |")
    return "\n".join(lines)


def score_table(label: str, statements, predicted, splits) -> list[str]:
    lines = []
    for split in splits:
        ss = [s for s in statements if s.split == split]
        for d in DEFECTS + ("all (micro)",):
            c = scoring.micro(ss, predicted) if d == "all (micro)" else scoring.confusion(ss, predicted, d)
            r = scoring.rates(c)
            lines.append(f"| {label} | {split} | {d} | {c.tp + c.fn} | {c.tp} | {c.fp} | {c.fn} | "
                         f"{pct(r.precision)}{ci(r.precision_ci)} | {pct(r.recall)}{ci(r.recall_ci)} |")
    return lines


HEADER = ["| Detector | Split | Defect | Positives | TP | FP | FN | Precision (95% CI) | Recall (95% CI) |",
          "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]


def render_offline(statements, lexicons, splits) -> str:
    lines = list(HEADER)
    for lex in lexicons:
        lines += score_table(lex.version, statements, detector.predict(statements, lex), splits)
    return "\n".join(lines)


def render_errors(statements, lexicon, split) -> str:
    predicted = detector.predict(statements, lexicon)
    lines = [f"Errors of `{lexicon.version}` on {split}:"]
    for s in statements:
        if s.split != split:
            continue
        missed = sorted(s.defects - predicted[s.id])
        false = sorted(predicted[s.id] - s.defects)
        if missed or false:
            lines.append(f"- {s.id} ({s.set}) miss: {', '.join(missed) or '-'}; false alarm: {', '.join(false) or '-'}"
                         f" — {s.text}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Requirement-defect detector evaluation")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--lexicon", type=Path, action="append", required=True)
    ap.add_argument("--split", choices=SPLITS + ("both",), default="both")
    ap.add_argument("--errors", choices=SPLITS)
    ap.add_argument("--live", help="a Claude model ID (costs money)")
    ap.add_argument("--max-usd", type=float, default=1.00, help="live-mode cost ceiling (default $1.00)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page

    statements = load_statements(args.data)
    lexicons = [load_lexicon(p) for p in args.lexicon]
    splits = SPLITS if args.split == "both" else (args.split,)
    print(dataset_table(statements))
    print()
    print(render_offline(statements, lexicons, splits))
    if args.errors:
        print("\n" + render_errors(statements, lexicons[-1], args.errors))
    if args.live:
        from . import live, models
        model = models.live_model(args.live)
        targets = [s for s in statements if s.split in splits]
        records = live.run_live(model, targets, statements, args.max_usd)
        predicted = {r.statement_id: r.flagged for r in records}
        outcomes = Counter(r.outcome for r in records)
        print(f"\nLive model `{model.name}` (prompt `{live.prompt.PROMPT_VERSION}`), ceiling ${args.max_usd:.2f}, "
              f"spent ${sum(r.cost_usd for r in records):.4f}; outcomes: "
              + ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items())))
        print("\n".join(HEADER + score_table(model.name, targets, predicted, splits)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

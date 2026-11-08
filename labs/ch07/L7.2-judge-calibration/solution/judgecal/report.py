"""Calibrate an LLM judge against human labels: the reports Chapter 7 quotes.

Offline (default, free, deterministic; both judges are SIMULATED):
    python -m judgecal.report --data ../data agreement
    python -m judgecal.report --data ../data probes
    python -m judgecal.report --data ../data decide

Live (costs money; needs `pip install -e ".[live]"` and credentials):
    python -m judgecal.report --data ../data decide --live judge-v2 --model claude-opus-5-5 --max-usd 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import calibrate, judges, policy

JUDGES = ["judge-v1", "judge-v2"]


def verify_pin(data: Path, pol: dict) -> str:
    m = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    if (m["name"], m["version"]) != (pol["dataset"]["name"], pol["dataset"]["version"]):
        raise SystemExit(f"policy pins {pol['dataset']}; data is {m['name']} {m['version']}")
    for name, digest in m["files"].items():
        text = (data / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        if hashlib.sha256(text).hexdigest() != digest:
            raise SystemExit(f"{name} does not match the manifest: a changed dataset is a new version")
    return f"{m['name']} {m['version']}"


def load(data: Path):
    return calibrate.load(data / "answers.jsonl"), calibrate.load(data / "pairs.jsonl")


def report_agreement(answers, pairs) -> str:
    lines = ["| Judge | Split | Answers | Accuracy | Cohen's kappa (95%) | Humans' kappa | TP | FP | FN | TN | False-pass rate |",
             "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for split in ("calibration", "heldout"):
        for name in JUDGES:
            c = calibrate.calibrate(judges.SimulatedJudge(name), answers, pairs, split)
            k = c.confusion
            lines.append(f"| {name} | {split} | {c.items} | {k.accuracy:.1%} | {c.kappa:.2f} "
                         f"({c.kappa_ci[0]:.2f} to {c.kappa_ci[1]:.2f}) | {c.human_kappa:.2f} | "
                         f"{k.tp} | {k.fp} | {k.fn} | {k.tn} | {k.false_pass_rate:.1%} |")
    return "\n".join(lines)


def report_probes(answers, pairs, split: str = "heldout") -> str:
    cs = [calibrate.calibrate(judges.SimulatedJudge(n), answers, pairs, split) for n in JUDGES]
    head = "| Probe | " + " | ".join(c.judge for c in cs) + " |"
    lines = [f"Bias probes on the {split} split (SIMULATED judges; biases are configured)", "",
             head, "| --- |" + " ---: |" * len(cs)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(c) for c in cs) + " |")

    n = cs[0].false_pass_n
    row(f"False passes, concise wrong answers (n={n['concise']})", lambda c: f"{c.false_pass['concise']:.1%}")
    row(f"False passes, verbose wrong answers (n={n['verbose']})", lambda c: f"{c.false_pass['verbose']:.1%}")
    row("Verbosity gap (points)", lambda c: f"{c.verbosity_gap * 100:+.1f}")
    row(f"False passes, wrong answers by the judge's own family (n={n['own family']})",
        lambda c: f"{c.false_pass['own family']:.1%}")
    row(f"False passes, wrong answers by the other family (n={n['other family']})",
        lambda c: f"{c.false_pass['other family']:.1%}")
    row("Self-preference gap (points)", lambda c: f"{c.self_preference_gap * 100:+.1f}")
    row(f"Pairs: first-shown answer chosen (of {2 * cs[0].pairs} verdicts)", lambda c: f"{c.first_position_rate:.1%}")
    row("Pairs: same answer chosen in both orders", lambda c: f"{c.swap_consistency:.1%}")
    row("Pairs: agrees with humans, one order", lambda c: f"{c.pair_accuracy:.1%}")
    row("Pairs: both orders agree (decided)", lambda c: f"{c.both_orders_decided:.1%}")
    row("Pairs: agrees with humans where decided", lambda c: f"{c.both_orders_accuracy:.1%}")
    return "\n".join(lines)


def report_decide(answers, pairs, pol: dict, judge_objs=None) -> str:
    judge_objs = judge_objs or [judges.SimulatedJudge(n) for n in JUDGES]
    lines = [f"Policy `{pol['policy']}` on the {pol['decide_on']} split"]
    for j in judge_objs:
        c = calibrate.calibrate(j, answers, pairs, pol["decide_on"])
        for d in policy.decide(pol, c):
            verdict = "MAY REPLACE HUMANS" if d.allowed else "KEEP HUMANS"
            lines += ["", f"{j.name}, {d.use}: **{verdict}**"]
            lines += [f"  {'ok  ' if x.ok else 'FAIL'} {x.name}: {x.detail}" for x in d.checks]
    lines += ["", "After approval: " + "; ".join(pol["after_approval"]) + "."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge calibration (Lab 7.2)")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("command", choices=["agreement", "probes", "decide"])
    ap.add_argument("--split", default="heldout", choices=["calibration", "heldout"], help="for probes")
    ap.add_argument("--live", choices=JUDGES, help="run this judge prompt on a real model (costs money)")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--max-usd", type=float, default=0.0)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pol = policy.load_policy(args.data / "judge-policy.json")
    pinned = verify_pin(args.data, pol)
    answers, pairs = load(args.data)
    if args.live:
        if args.command != "decide" or args.max_usd <= 0:
            print("live mode runs `decide` and needs --max-usd", file=sys.stderr)
            return 2
        j = judges.ClaudeJudge(args.live, args.model, args.max_usd)
        print(f"Dataset {pinned}; live judge {args.live} on {args.model}")
        print(report_decide(answers, pairs, pol, [j]))
        print(f"\nSpend ${j.spent_usd:.4f}; outcomes other than a verdict: {j.outcomes or 'none'}")
        return 0
    print({"agreement": lambda: report_agreement(answers, pairs),
           "probes": lambda: report_probes(answers, pairs, args.split),
           "decide": lambda: report_decide(answers, pairs, pol)}[args.command]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

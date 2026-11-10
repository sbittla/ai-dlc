"""Lab 15.1's reports (provided). Run from starter/ or solution/:

    python -m pipeline.report lint                 # Relay 4.29.0's workflows and the agent's two drafts
    python -m pipeline.report guard                # the incident's pull request and three others
    python -m pipeline.report incident             # the composite incident of 1 to 10 March 2027
    python -m pipeline.report candidates           # twelve candidates for 4.29.0, deliver mode
    python -m pipeline.report train                # verify-only beside the 15:00 UTC train, 22 March to 30 April
    python -m pipeline.report matrix --as-of DATE  # coverage of every class on that date's code
    python -m pipeline.report g4 --as-of DATE      # Gate G4's adversarial row on that date
    python -m pipeline.report timeline             # the row on four dates

`candidates --id P-07 --mode verify-only` shows one candidate's stages. Exit status: `g4` exits 1 when the row
is not met; `guard --pr N` exits with the guard's code (0 pass, 1 block, 2 cannot decide).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import DATA, RELAY, load_json, yamlish
from .adversarial import counted, coverage, gate, matrix_as_of
from .g4 import g4_row
from .guard import decision, guard
from .lint import lint
from .stages import GATES, run_pipeline

TIMELINE = ("2027-03-22", "2027-03-31", "2027-04-27", "2027-04-30")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _dur(seconds: float) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    return f"{d} d {h} h {rem // 60} min"


def lint_rows() -> list[tuple[str, list]]:
    paths = sorted((RELAY / ".github" / "workflows").glob("*.yml")) + sorted((DATA / "drafts").glob("*.yml"))
    out = []
    for p in paths:
        rel = p.relative_to(RELAY).as_posix() if RELAY in p.parents else p.relative_to(DATA.parent).as_posix()
        out.append((rel, lint(yamlish.loads(p.read_text(encoding="utf-8")), p.name)))
    return out


def report_lint() -> str:
    lines = ["# Pipeline lint (PL001-PL010)", "", "| Workflow | Findings | Rules |", "| --- | ---: | --- |"]
    details = []
    for rel, fs in lint_rows():
        rules = Counter(f.rule for f in fs)
        lines.append(f"| `{rel}` | {len(fs)} | {', '.join(f'{r}×{n}' if n > 1 else r for r, n in sorted(rules.items())) or '—'} |")
        details += [f"- {f.rule} {f.where}: {f.message}" for f in fs]
    return "\n".join(lines + [""] + details) + "\n"


def teams():
    return load_json(DATA / "teams.json")


def guard_policy():
    return load_json(RELAY / "governance" / "pipeline-guard.json")


def required():
    return load_json(RELAY / "governance" / "branch-protection.json")["required_status_checks"]["contexts"]


def all_prs() -> list[dict]:
    return [load_json(DATA / "incident" / "pr-2604.json")] + [load_json(p) for p in sorted((DATA / "prs").glob("*.json"))]


def guard_pr(pr: dict):
    t = None if pr.get("teams_unavailable") else teams()
    findings = guard(pr, guard_policy(), t, required())
    return findings, decision(findings)


def report_guard(number: int | None = None) -> tuple[str, int]:
    lines = ["# Pipeline guard (relay-pipeline-guard-v1)", "", "| PR | Title | Decision | Findings |",
             "| ---: | --- | --- | --- |"]
    details, code = [], 0
    for pr in all_prs():
        if number is not None and pr["number"] != number:
            continue
        fs, (verdict, code) = guard_pr(pr)
        lines.append(f"| #{pr['number']} | {pr['title'][:60]} | {verdict} | {', '.join(f.rule for f in fs) or '—'} |")
        details += [f"- #{pr['number']} {f.rule} {f.where}: {f.message}" for f in fs]
    return "\n".join(lines + [""] + details) + "\n", code


def incident_numbers() -> dict:
    t = load_json(DATA / "incident" / "timeline.json")
    ev = {e["what"].split(":")[0][:40]: e["at"] for e in t["events"]}
    at = [e["at"] for e in t["events"]]
    merged = t["merged_while_blind"]
    pr = load_json(DATA / "incident" / "pr-2604.json")
    fs, (verdict, _) = guard_pr(pr)
    return {"first_failure": at[0], "agent_commit": at[2], "approved": at[4], "merged": at[5], "noticed": at[6],
            "reverted": at[7], "blind": (_ts(at[7]) - _ts(at[5])).total_seconds(),
            "to_notice": (_ts(at[6]) - _ts(at[5])).total_seconds(), "merged_prs": len(merged),
            "empty_reports": sum(m["trivy_report"] == "empty" for m in merged),
            "would_block": [m for m in merged if m["would_block"]], "guard": verdict,
            "guard_rules": [f.rule for f in fs], "lint_after": [f.rule for f in lint(yamlish.loads(
                (DATA / "incident" / "ci-after.yml").read_text(encoding="utf-8")), "ci-after.yml")],
            "events": t["events"], "_unused": ev}


def report_incident() -> str:
    n = incident_numbers()
    lines = ["# The March 2027 incident (composite; generated)", ""]
    lines += [f"- {e['at']}  {e['what']}" for e in n["events"]]
    lines += ["", f"Agent's commit to merge: {_dur((_ts(n['merged']) - _ts(n['agent_commit'])).total_seconds())}",
              f"Merge to revert (no reliable Trivy result): {_dur(n['blind'])}",
              f"Merge to someone noticing: {_dur(n['to_notice'])}",
              f"Pull requests merged meanwhile: {n['merged_prs']}; with an empty Trivy report: {n['empty_reports']}",
              f"Findings a working Trivy step would have blocked: {len(n['would_block'])}"]
    lines += [f"  - #{m['number']}: {m['would_block']}" for m in n["would_block"]]
    lines += ["", f"Pipeline guard on #2604: {n['guard']} ({', '.join(n['guard_rules'])})",
              f"Pipeline lint on the changed ci.yml (a state check, not a diff): "
              f"{', '.join(n['lint_after']) or 'no findings'}"]
    return "\n".join(lines) + "\n"


def runs(folder: str, mode: str) -> list:
    policy = load_json(RELAY / "deploy" / "admission" / "policy.json")
    trust = load_json(DATA / "trust-root.json")
    return [(c, run_pipeline(c, mode, policy, trust))
            for c in (load_json(p) for p in sorted((DATA / folder).glob("*.json")))]


def report_candidates(mode: str = "deliver", only: str | None = None) -> str:
    lines = [f"# Release candidates for Relay 4.29.0 ({mode})", "",
             "| Candidate | What is wrong | Outcome | Detail |", "| --- | --- | --- | --- |"]
    for c, run in runs("candidates", mode):
        if only and c["id"] != only:
            continue
        bad = run.first_failure
        lines.append(f"| {c['id']} | {c['description']} | {run.outcome} | {bad.detail[:90] if bad else '—'} |")
        if only:
            lines += [""] + [f"- {s.name}: {s.status} — {s.detail}" for s in run.stages]
    return "\n".join(lines) + "\n"


def train_numbers() -> dict:
    rs = runs("train", "verify-only")
    first = Counter(r.first_failure.name for _, r in rs if r.first_failure)
    anyfail = Counter(s.name for _, r in rs for s in r.stages if s.status in ("fail", "error"))
    agree = [c["id"] for c, r in rs if not r.first_failure]
    return {"releases": len(rs), "shipped": sum(c["train"]["shipped"] for c, _ in rs), "would_deploy": agree,
            "first": dict(first), "any": dict(anyfail), "rows": rs}


def report_train() -> str:
    n = train_numbers()
    lines = ["# Verify-only beside the 15:00 UTC deploy train, 22 March to 30 April 2027 (generated)", "",
             f"Train deployments: {n['releases']} (all shipped by the train)",
             f"The pipeline would have deployed: {len(n['would_deploy'])} ({', '.join(n['would_deploy'])})", "",
             "| Stage | Releases it would have stopped (first failure) | Releases it failed at all |",
             "| --- | ---: | ---: |"]
    for stage in ("build",) + GATES + ("release", "admit"):
        lines.append(f"| {stage} | {n['first'].get(stage, 0)} | {n['any'].get(stage, 0)} |")
    lines += ["", "| Release | Outcome | First failure |", "| --- | --- | --- |"]
    for c, r in n["rows"]:
        bad = r.first_failure
        lines.append(f"| {c['id']} | {r.outcome} | {bad.detail[:80] if bad else '—'} |")
    return "\n".join(lines) + "\n"


def report_matrix(as_of: str) -> str:
    m = matrix_as_of("4.29.0", as_of)
    cov = coverage(m)
    passed, reasons = gate(m)
    lines = [f"# Coverage on the code of {as_of} (relay-coverage-gate-v2)", "",
             "| Class | Harm | Verified controls | Coverage |", "| --- | --- | --- | ---: |"]
    for cls in m.classes:
        ver = [c.control for c in m.row(cls["id"]) if c.status == "verified"]
        lines.append(f"| {cls['id']} | {cls['harm']} | {', '.join(ver) or '—'} | {cov[cls['id']]} |")
    statuses = Counter(c.status for c in m.cells)
    lines += ["", f"Cells: {len(m.cells)} ({', '.join(f'{k} {v}' for k, v in sorted(statuses.items()))})",
              f"Counted controls: {len(counted(m))}", f"Gate: {'PASS' if passed else 'FAIL'}"]
    lines += [f"- {r}" for r in reasons]
    for cls_id in ("C10", "C14"):
        for c in m.row(cls_id):
            if c.control in ("test_sandbox", "human_label"):
                lines.append(f"- {cls_id} {c.control}: {c.status} — {c.evidence}")
    return "\n".join(lines) + "\n"


def g4_numbers(as_of: str) -> tuple[bool, list[str]]:
    return g4_row(matrix_as_of("4.29.0", as_of), load_json(DATA / "deployments.json")["records"], as_of)


def report_g4(as_of: str) -> tuple[str, int]:
    met, reasons = g4_numbers(as_of)
    lines = [f"# Gate G4's adversarial row as of {as_of}: {'MET' if met else 'NOT MET'}", ""]
    lines += [f"- {r}" for r in reasons]
    return "\n".join(lines) + "\n", 0 if met else 1


def report_timeline() -> str:
    lines = ["# Gate G4's adversarial row over time", "", "| Date | Coverage gate | Counted controls without "
             "deployment evidence | Row |", "| --- | --- | ---: | --- |"]
    for d in TIMELINE:
        m = matrix_as_of("4.29.0", d)
        passed, _ = gate(m)
        met, reasons = g4_row(m, load_json(DATA / "deployments.json")["records"], d)
        missing = sum("no deployment evidence" in r for r in reasons)
        short = [r.split(":")[0] for r in reasons if "independent verified" in r]
        lines.append(f"| {d} | {'PASS' if passed else 'FAIL (' + ', '.join(short) + ')'} | {missing} of "
                     f"{len(counted(m))} | {'MET' if met else 'NOT MET'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lab 15.1 reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lint")
    g = sub.add_parser("guard")
    g.add_argument("--pr", type=int)
    sub.add_parser("incident")
    c = sub.add_parser("candidates")
    c.add_argument("--mode", default="deliver")
    c.add_argument("--id")
    sub.add_parser("train")
    for name in ("matrix", "g4"):
        p = sub.add_parser(name)
        p.add_argument("--as-of", default="2027-04-30")
    sub.add_parser("timeline")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # tables use — and ×; Windows consoles default to cp1252
    code = 0
    if args.cmd == "lint":
        text = report_lint()
    elif args.cmd == "guard":
        text, code = report_guard(args.pr)
        code = code if args.pr is not None else 0
    elif args.cmd == "incident":
        text = report_incident()
    elif args.cmd == "candidates":
        text = report_candidates(args.mode, args.id)
    elif args.cmd == "train":
        text = report_train()
    elif args.cmd == "matrix":
        text = report_matrix(args.as_of)
    elif args.cmd == "g4":
        text, code = report_g4(args.as_of)
    else:
        text = report_timeline()
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())

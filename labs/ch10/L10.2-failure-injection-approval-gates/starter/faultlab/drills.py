"""Run the failure-injection drills in data/faults.json and judge each one (verdict is TODO 3)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from relay.agents import ApprovalRefused, Budget, apply_budget_raise
from relay.audit import verify

from . import DATA_DIR
from .helper import REQUESTER, Crash, ModelUnavailable, Process, World, raised
from .recover import ResumeRefused, resume, start


def load() -> dict:
    return json.loads((DATA_DIR / "faults.json").read_text(encoding="utf-8"))


def policy_ok(records: list[dict], pulls: list[dict]) -> bool:
    """Every pull request on GitHub carries a diff a person approved, and was opened only after that approval.

    The diff is the one GitHub holds, not one an agent reported. The approved diffs come from the audit trail:
    each `approval.request` names the diff it is bound to, and an approved `approval.decide` accepts it.
    """
    requested, bound, approved_args, approved_diffs = {}, {}, set(), set()
    for r in records:
        d = r["detail"]
        if r["action"] == "approval.request":
            requested[d["approval_id"]] = d["args_sha256"]
            bound[d["approval_id"]] = d.get("bound", {}).get("diff_sha256")
        elif r["action"] == "approval.decide" and r["outcome"] == "approved":
            approved_args.add(requested.get(d["approval_id"]))
            approved_diffs.add(bound.get(d["approval_id"]))
        elif r["action"] == "tool.open_pull_request" and r["outcome"] == "ok" and d["args_sha256"] not in approved_args:
            return False
    return all(pull["diff_sha256"] in approved_diffs for pull in pulls)


def run_drill(drill: dict, cfg: dict, folder: Path, blind: bool = False) -> dict:
    procs: list[Process] = []
    try:
        return _run_drill(drill, cfg, folder, blind, procs)
    finally:
        for p in procs:
            p.store.close()


def _run_drill(drill: dict, cfg: dict, folder: Path, blind: bool, procs: list) -> dict:
    world = World(drill["fault"], cfg["task"], blind=blind)
    budget = Budget(**cfg["budget"])
    if drill["fault"] == "budget_exhausted":
        budget = Budget(max_steps=cfg["budget"]["max_steps"], max_usd=0.06, max_seconds=cfg["budget"]["max_seconds"])
    db = folder / f"{drill['id']}{'-blind' if blind else ''}.db"
    decisions = [list(d) for d in drill["decisions"]]
    key = f"{drill['id']}:{cfg['task']['task_id']}"
    resumes, refused, usd_at_interrupt = 0, [], None
    procs.append(Process(world, db, budget))
    proc = procs[0]
    run_id = None
    first = True
    while True:
        try:
            if first:
                first = False
                result = start(proc, key)
                run_id = proc.run_id
                if drill["fault"] == "duplicate_trigger":
                    procs.append(Process(world, db, budget))
                    assert start(procs[-1], key) is None  # the second trigger starts nothing
            else:
                proc = Process(world, db, budget)
                procs.append(proc)
                result = resume(proc, run_id)
        except (Crash, ModelUnavailable):
            run_id = run_id or proc.run_id
            resumes += 1
            usd_at_interrupt = proc.store.run(run_id)["checkpoint"].get("meter", {}).get("usd", 0.0)
            world.person_proof = world.person(REQUESTER)  # the requester restarts the job
            continue
        if result.status != "awaiting_approval" or not decisions:
            break
        decided = None
        while decisions and decided is None:
            decision = decisions.pop(0)
            if decision[0] == "wait_hours":
                world.clock.t += decision[1] * 3600
                continue
            _, person, choice = decision
            try:  # each person decides with their own fresh proof
                decided = proc.gate.decide(result.approval_id, world.person(person), choice == "approve",
                                           f"drill {drill['id']}")
            except ApprovalRefused as exc:
                refused.append(exc.code)
                if exc.code == "expired":  # the request is gone; resuming asks again
                    break
        if decided is not None and result.reason == "raise_budget" and decided.status == "approved":
            usd_at_interrupt = proc.meter.usd
            apply_budget_raise(proc.gate, run_id, raised(Budget(**proc.store.run(run_id)["budget"])))
        if decided is not None and decided.tool == "open_pull_request" and world.approved_diff is None:
            world.approved_diff = bound_diff(world.trail.records, decided.approval_id)
            if drill["fault"] in ("diff_changed_after_approval", "steered_after_approval"):
                cp = proc.store.run(run_id)["checkpoint"]  # the agent edits again before opening the pull request
                f = cfg["task"]["files"][0]
                content = "MALICIOUS\n" if drill["fault"] == "steered_after_approval" else f"version 2 of {f}\n"
                cp["plan"][cp["pos"]:cp["pos"]] = [["edit_file", {"path": f, "content": content}],
                                                   ["run_tests", {"target": "approved"}]]
                proc.store.save_checkpoint(run_id, cp, world.clock.stamp())
        world.person_proof = world.person(REQUESTER)  # the requester resumes the run, with a fresh proof
    run = proc.store.run(run_id)
    resume_refused = False
    if drill["fault"] == "kill_switch":
        procs.append(Process(world, db, budget))
        try:
            resume(procs[-1], run_id)
        except ResumeRefused:
            resume_refused = True
    steps = proc.store.steps(run_id)
    requests = [r for r in world.trail.records
                if r["action"] == "approval.request" and r["detail"]["tool"] == "open_pull_request"]
    final_usd = run["checkpoint"]["meter"]["usd"]
    return {
        "id": drill["id"], "title": drill["title"], "status": run["status"], "reason": run["reason"],
        "pulls": len(world.github.pulls), "github_creates": world.github.creates, "resumes": resumes,
        "runs": proc.store.conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0],
        "approval_requests": len(requests), "refused_decisions": refused, "resume_refused": resume_refused,
        "budget_carried": usd_at_interrupt is not None and final_usd > usd_at_interrupt > 0,
        "codeowners_changed": world.files[".github/CODEOWNERS"] != "original .github/CODEOWNERS\n",
        "malicious_in_pr": any(pull["diff_sha256"] == world.diff_sha() for pull in world.github.pulls)
        and "MALICIOUS" in "".join(world.files.values()),
        "refusals": sorted({s["result"]["code"] for s in steps if s["outcome"] == "refused"}),
        "revoked_call_recorded": any(r["detail"].get("code") == "revoked:disabled" for r in world.trail.records),
        "usd": round(final_usd, 4), "steps": len(steps), "audit_records": len(world.trail.records),
        "trail_ok": verify(world.trail.records).ok, "policy_ok": policy_ok(world.trail.records, world.github.pulls),
    }


def bound_diff(records: list[dict], approval_id: str) -> str | None:
    for r in records:
        if r["action"] == "approval.request" and r["detail"]["approval_id"] == approval_id:
            return r["detail"].get("bound", {}).get("diff_sha256")
    return None


def verdict(outcome: dict, expect: dict) -> list[str]:
    """What the drill got wrong, as "key: expected X, got Y" lines; an empty list means it passed.

    For each key in `expect`, in the order given: for "refusals", every expected code must be in the
    outcome's list; for any other key, the outcome's value must equal the expected one. Then, whatever
    `expect` says, the audit trail must verify ("trail_ok: expected True, got False") and every pull
    request must have been approved first ("policy_ok: expected True, got False").
    """
    raise NotImplementedError("TODO 3: verdict (Lab 10.2 step 4)")


def run_all() -> list[tuple[dict, list[str]]]:
    cfg = load()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        return [(o, verdict(o, d["expect"])) for d in cfg["drills"] for o in [run_drill(d, cfg, Path(tmp))]]


def run_blind(drill_id: str = "D02") -> dict:
    """The same drill with a handler that creates without looking first: what idempotency prevents."""
    cfg = load()
    drill = next(d for d in cfg["drills"] if d["id"] == drill_id)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        return run_drill(drill, cfg, Path(tmp), blind=True)

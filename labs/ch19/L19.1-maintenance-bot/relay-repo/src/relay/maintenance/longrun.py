"""Long-running maintenance: checkpoints, budgets, cancellation and escalation (added in 4.31.0; ADR-055).

A campaign is maintenance work too large for one run: refresh every dependency of a service, extend a table for
fourteen zones, re-check two hundred documentation links. It is built from parts Relay already has rather than a
new scheduler:

- **One run, many jobs.** The campaign is one run in Chapter 10's `RunStore` (its budget, status and checkpoint
  live there). Each item is a job on Chapter 18's `AgentJobQueue`, keyed `<campaign>:<item>`, so a repeated start
  adds nothing and a crashed worker's item is claimed again after its lease.
- **Checkpoints.** After each item the worker heartbeats the item's job, then saves the campaign's meter and
  counts to the run. A new process resumes from the last checkpoint: what was spent stays spent.
- **Budgets.** Chapter 10's `Meter` admits an item only if its estimate fits what is left. When it does not,
  the campaign waits (`awaiting_approval`, reason `budget:<kind>`) and escalates. Only a person other than the
  campaign's requester may raise it (`request_budget_raise`, `decide_raise`, which audits a refusal, and
  `apply_budget_raise`).
- **Cancellation.** A person, authenticated by their own proof, cancels: queued items are cancelled at once and
  a running one at its next heartbeat, between steps, never inside an effect. The run ends as `stopped`.
- **Escalation.** Three items handed back in a row, a sandbox refusal, or the budget: the campaign stops taking
  items and writes `maintenance.escalate` to the audit trail with the reason, for the bot's owner.

Times are seconds passed in by the caller, so tests control the clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..agents import ApprovalGate, Budget, BudgetExceeded, Meter, RunStore
from ..agentops.jobs import AgentJobQueue, JobCancelled, LeaseLost
from ..audit import AuditTrail

KIND = "maintenance-item"
REPEAT_LIMIT = 3


@dataclass(frozen=True)
class ItemResult:
    status: str            # done, handed_back, refused
    usd: float
    seconds: float
    note: str = ""


@dataclass
class CampaignResult:
    status: str            # finished, awaiting_approval, handed_back, stopped
    reason: str
    done: list[str] = field(default_factory=list)
    handed_back: list[str] = field(default_factory=list)
    usd: float = 0.0


class Campaign:
    def __init__(self, campaign_id: str, store: RunStore, queue: AgentJobQueue, trail: AuditTrail, gate: ApprovalGate,
                 agent_id: str, owner: str, requester: str, stamp: Callable[[], str]) -> None:
        self.campaign_id, self.store, self.queue, self.trail, self.gate = campaign_id, store, queue, trail, gate
        self.agent_id, self.owner, self.requester, self.stamp = agent_id, owner, requester, stamp
        self.run_id = f"run-campaign:{campaign_id}"

    def _audit(self, action: str, outcome: str, **detail) -> None:
        self.trail.append(agent_id=self.agent_id, owner=self.owner, on_behalf_of=self.requester, action=action,
                          resource=f"campaign:{self.campaign_id}", outcome=outcome, source="relay.maintenance",
                          at=self.stamp(), detail=detail)

    def start(self, items: list[dict], budget: Budget, now: float) -> None:
        """Create the run and one job per item. Each item needs `item_id` and `estimate_usd`. Safe to repeat."""
        run_id, created = self.store.start_run(f"campaign:{self.campaign_id}", self.campaign_id, "campaign",
                                               self.agent_id, self.requester, self.stamp(),
                                               {"max_steps": budget.max_steps, "max_usd": budget.max_usd,
                                                "max_seconds": budget.max_seconds})
        for it in items:
            self.queue.enqueue(KIND, f"{self.campaign_id}:{it['item_id']}", dict(it), now)
        if created:
            self.store.save_checkpoint(run_id, {"meter": {}, "done": [], "handed_back": [], "streak": 0},
                                       self.stamp())
            self._audit("maintenance.campaign", "started", items=len(items))

    def _meter(self) -> tuple[Meter, dict]:
        run = self.store.run(self.run_id)
        b = run["budget"]
        meter = Meter(Budget(int(b["max_steps"]), float(b["max_usd"]), float(b["max_seconds"])))
        meter.restore(run["checkpoint"].get("meter", {}))
        return meter, run

    def _escalate(self, status: str, reason: str, cp: dict, meter: Meter) -> CampaignResult:
        if self.store.run(self.run_id)["status"] not in ("stopped", "finished", "handed_back"):
            self.store.set_status(self.run_id, status, reason, self.stamp())
        self._audit("maintenance.escalate", status, reason=reason, usd=round(meter.usd, 6),
                    done=len(cp["done"]), handed_back=len(cp["handed_back"]))
        return CampaignResult(status, reason, list(cp["done"]), list(cp["handed_back"]), meter.usd)

    def run(self, worker_id: str, handle: Callable[[dict], ItemResult], clock: Callable[[], float],
            lease_s: float = 120.0, crash_after: int | None = None) -> CampaignResult:
        """Work through the items until done, a stop or an escalation. `crash_after` (tests only) ends the
        process after that many items, without a goodbye, to show what a restart resumes."""
        meter, run = self._meter()
        if run["status"] == "stopped":
            return CampaignResult("stopped", run["reason"] or "", run["checkpoint"]["done"],
                                  run["checkpoint"]["handed_back"], meter.usd)
        if run["status"] == "awaiting_approval":
            self.store.set_status(self.run_id, "running", None, self.stamp())  # resumed after a raise
        cp = dict(run["checkpoint"])
        cp.setdefault("streak", 0)
        processed = 0
        while True:
            try:
                meter.check()
            except BudgetExceeded as exc:
                return self._escalate("awaiting_approval", f"budget:{exc.kind}", cp, meter)
            if self.store.run(self.run_id)["status"] == "stopped":  # a person cancelled between items
                return CampaignResult("stopped", "cancelled", list(cp["done"]), list(cp["handed_back"]), meter.usd)
            job = self.queue.claim(worker_id, clock(), lease_s, kinds=(KIND,))
            if job is None:
                self.store.set_status(self.run_id, "finished", "all items processed", self.stamp())
                self._audit("maintenance.campaign", "finished", usd=round(meter.usd, 6), done=len(cp["done"]),
                            handed_back=len(cp["handed_back"]))
                return CampaignResult("finished", "all items processed", list(cp["done"]),
                                      list(cp["handed_back"]), meter.usd)
            item = job.payload
            try:
                meter.admit(float(item.get("estimate_usd", 0.0)))
            except BudgetExceeded as exc:  # give the item back untouched: it is done after a raise, not now
                self.queue.park(job.id, job.lease_token, f"budget:{exc.kind}", clock())
                self.queue.wake(job.id, clock(), self.agent_id)
                return self._escalate("awaiting_approval", f"budget:{exc.kind}", cp, meter)
            result = handle(item)
            meter.steps += 1
            meter.usd += result.usd
            meter.seconds += result.seconds
            try:
                self.queue.heartbeat(job.id, job.lease_token, clock(), lease_s)  # before the checkpoint
            except JobCancelled:
                cp["meter"] = meter.snapshot()
                self.store.save_checkpoint(self.run_id, cp, self.stamp())
                return self._escalate("stopped", "cancelled", cp, meter)
            except LeaseLost:
                return CampaignResult("running", "lease_lost", list(cp["done"]), list(cp["handed_back"]), meter.usd)
            if result.status == "done":
                cp["done"] = cp["done"] + [item["item_id"]]
                cp["streak"] = 0
            else:
                cp["handed_back"] = cp["handed_back"] + [item["item_id"]]
                cp["streak"] += 1
            cp["meter"] = meter.snapshot()
            self.store.save_checkpoint(self.run_id, cp, self.stamp())
            self.queue.complete(job.id, job.lease_token, {"status": result.status, "note": result.note[:200]},
                                clock())
            if result.status == "refused":
                self._cancel_open(clock(), self.agent_id)
                return self._escalate("handed_back", f"sandbox_refused:{item['item_id']}", cp, meter)
            if cp["streak"] >= REPEAT_LIMIT:
                self._cancel_open(clock(), self.agent_id)
                return self._escalate("handed_back", "repeated_hand_back", cp, meter)
            processed += 1
            if crash_after is not None and processed >= crash_after:
                return CampaignResult("running", "crashed", list(cp["done"]), list(cp["handed_back"]), meter.usd)

    def _open_jobs(self) -> list[int]:
        rows = self.queue.conn.execute(
            "SELECT id FROM agent_jobs WHERE kind = ? AND dedup_key LIKE ? AND status IN "
            "('queued', 'running', 'waiting') ORDER BY id", (KIND, f"{self.campaign_id}:%")).fetchall()
        return [r[0] for r in rows]

    def _cancel_open(self, now: float, actor: str) -> None:
        for job_id in self._open_jobs():
            self.queue.cancel(job_id, actor, now)

    def decide_raise(self, approval_id: str, proof: dict, approve: bool, reason: str):
        """A person decides a budget raise (Chapter 10's `another_person` rule). Chapter 10's gate raises on a
        refusal without writing it down; here every refusal is audited first, then raised."""
        from ..agents import ApprovalRefused
        try:
            decision = self.gate.decide(approval_id, proof, approve, reason)
        except ApprovalRefused as exc:
            self._audit("maintenance.budget_raise", "refused", code=exc.code, approval_id=approval_id)
            raise
        self._audit("maintenance.budget_raise", decision.status, approval_id=approval_id,
                    decided_by=decision.decided_by)
        return decision

    def cancel(self, proof: dict, now: float) -> str:
        """A person stops the campaign. Their proof is checked like an approval's; a refusal is audited."""
        from ..agents import ApprovalRefused
        try:
            person = self.gate.authenticate(proof)
        except ApprovalRefused as exc:
            self._audit("maintenance.cancel", "refused", code=exc.code)
            raise
        self._cancel_open(now, person)
        run = self.store.run(self.run_id)
        if run["status"] in ("running", "awaiting_approval"):
            self.store.set_status(self.run_id, "stopped", "cancelled", self.stamp())
        self._audit("maintenance.cancel", "ok", person=person)
        return "stopped"

"""Kill-switch drills: Relay's side run in process on a simulated clock (reference solution).

A drill issues a real Relay agent token to a simulated agent, lets that agent and a client holding a
copy of the token call a gateway every few seconds, raises an alert, trips the kill switch, and records
every request's outcome. The gateway may cache verification results, as many API gateways and services
do; the cache is the variable the first two drills compare.

What a drill here does not measure: anything outside Relay. The cloud-side steps (starting the
kill-switch workflow, attaching the quarantine policy, IAM propagation, stopping tasks or runs) take the
ASSUMED durations in data/drill/assumptions.json. A live drill must replace them with measurements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from relay.audit import AUDIENCE, AgentRegistry, AuditTrail, KillSwitchResult, TokenRejected, TokenService, trip

DRILL_KEY = b"lab14.1-drill-signing-key-not-a-secret-0000"  # a fixed key for a simulation, not a secret


@dataclass(frozen=True)
class Outcome:
    client: str
    at: datetime
    accepted: bool
    code: str  # "ok", "ok (cached)" or the refusal code


@dataclass(frozen=True)
class DrillRun:
    drill_id: str
    agent: str
    kind: str
    alert_at: datetime
    trip_at: datetime
    outcomes: tuple[Outcome, ...]
    refresh: str  # the outcome of the agent's attempt to get a new token after the trip
    switch: KillSwitchResult
    has_cloud_role: bool
    has_github_app: bool


def _at(day: str, hhmmss: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time.fromisoformat(hhmmss), tzinfo=timezone.utc)


def run_drill(drill: dict, assumptions: dict, registry_path: Path) -> DrillRun:
    registry = AgentRegistry.load(registry_path)
    agent = registry.get(drill["agent"])
    now = {"t": _at(drill["date"], drill["token_issued_at"])}
    service = TokenService(registry, DRILL_KEY, clock=lambda: now["t"].timestamp(), new_id=lambda: "drill")
    trail = AuditTrail(clock=lambda: now["t"].strftime("%Y-%m-%dT%H:%M:%SZ"))
    registry_people_issuer = registry.person_issuer

    def proofs():
        # Fresh, simulated proofs: the workload's, and the person's for an agent that acts for someone.
        t = now["t"].timestamp()
        workload = {"iss": agent.issuer, "sub": agent.subject, "aud": AUDIENCE, "iat": t}
        person = None if drill["on_behalf_of"] is None else {
            "iss": registry_people_issuer, "sub": drill["on_behalf_of"], "aud": AUDIENCE, "iat": t}
        return workload, person

    workload, person = proofs()
    token, _ = service.exchange(workload, sorted(agent.scopes), subject=person)

    alert_at = _at(drill["date"], drill["alert_at"])
    trip_at = alert_at + timedelta(seconds=assumptions["alert_to_trip"])
    end_at = _at(drill["date"], drill["end_at"])
    refresh_at = _at(drill["date"], drill["refresh_at"])
    requests = []
    for c in drill["clients"]:
        t = _at(drill["date"], c["first_at"])
        while t <= end_at:
            requests.append((t, c["name"]))
            t += timedelta(seconds=c["interval_seconds"])
    requests.sort()

    cache: dict[str, datetime] = {}
    ttl = drill["gateway_cache_seconds"]
    outcomes, switch, refresh = [], None, None
    scope = sorted(agent.scopes)[0]
    for at, client in requests:
        now["t"] = at
        if switch is None and at >= trip_at:
            now["t"] = trip_at
            switch = trip(registry, trail, agent.agent_id, actor="detection:DR-001", reason=f"{drill['id']} (simulated)",
                          now=trip_at.timestamp())
            now["t"] = at
        if refresh is None and at >= refresh_at:
            now["t"] = refresh_at
            try:
                service.exchange(proofs()[0], sorted(agent.scopes), subject=proofs()[1])
                refresh = "ok"
            except TokenRejected as exc:
                refresh = exc.code
            now["t"] = at
        if ttl and token in cache and (at - cache[token]).total_seconds() < ttl:
            outcomes.append(Outcome(client, at, True, "ok (cached)"))
            continue
        try:
            service.verify(token, scope)
            cache[token] = at
            outcomes.append(Outcome(client, at, True, "ok"))
        except TokenRejected as exc:
            cache.pop(token, None)
            outcomes.append(Outcome(client, at, False, exc.code))
    return DrillRun(drill["id"], agent.agent_id, agent.kind, alert_at, trip_at, tuple(outcomes), refresh or "not tried",
                    switch, agent.cloud_role is not None, agent.github_app is not None)


def revocation_seconds(outcomes: tuple[Outcome, ...] | list[Outcome], alert_at: datetime) -> float | None:
    """Time to revoke: seconds from the alert to the first refused request after the last accepted one, over
    all clients. This is the one definition the chapter, the runbook and the requirement (at most 60 s) use.

    Only outcomes at or after the alert count. If a request is still accepted at the end of the drill
    (no refusal follows the last acceptance), return None: revocation did not happen in the window. If
    nothing at or after the alert was accepted, the first refusal at or after the alert is the answer.
    """
    later = sorted((o for o in outcomes if o.at >= alert_at), key=lambda o: o.at)
    accepted = [o.at for o in later if o.accepted]
    last_ok = accepted[-1] if accepted else None
    refused = [o.at for o in later if not o.accepted and (last_ok is None or o.at > last_ok)]
    if not refused:
        return None
    return (refused[0] - alert_at).total_seconds()


def cloud_seconds(assumptions: dict, kind: str, has_cloud_role: bool, has_github_app: bool = False) -> int:
    """ASSUMED seconds from the alert until everything outside Relay is done (provided): the trip delay, the
    kill-switch workflow's start, then the longest applicable branch (the agent's kind, its cloud role if it
    has one, its GitHub App if it has one), each branch's steps in order."""
    branches = [kind] + (["cloud_role"] if has_cloud_role else []) + (["github_app"] if has_github_app else [])
    longest = max(sum(s for _, s in assumptions["after_start"][b]) for b in branches)
    return assumptions["alert_to_trip"] + assumptions["workflow_start"] + longest


@dataclass(frozen=True)
class DrillResult:
    drill_id: str
    agent: str
    cache_seconds: int
    relay_seconds: float | None
    cloud_seconds: int
    passed: bool
    refresh: str


def judge(run: DrillRun, drill: dict, assumptions: dict, requirement: int) -> DrillResult:
    relay = revocation_seconds(run.outcomes, run.alert_at)
    cloud = cloud_seconds(assumptions, run.kind, run.has_cloud_role, run.has_github_app)
    ok = relay is not None and relay <= requirement and cloud <= requirement
    return DrillResult(run.drill_id, run.agent, drill["gateway_cache_seconds"], relay, cloud, ok, run.refresh)


def load_drills(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

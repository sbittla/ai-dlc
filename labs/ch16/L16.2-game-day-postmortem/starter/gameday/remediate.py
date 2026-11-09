"""The remediation gate (TODO 3: `Gate.decide`). Authenticated requests tied to a supported hypothesis, approvals
bound to one request, expiry, and an audit record of every refusal (ADR-039).

The catalogue (provided). `approvers` is how many distinct people must approve; `roles` the roles that count.
For a two-person action the approvers must between them cover every listed role, and the person who requested it
may be one of them (Relay's hotfix rule: the on-call engineer and a tech lead). For a one-person action the
approver must not be the requester. An agent identity may request an action; it never approves one, and it never
trips or restores a kill switch through this gate. Automated trips for DR-001 and DR-003 go through the monitor's
router, rate-limited and switchable, not through this gate.

Every proof is signed by the lab's issuer, under five minutes old, for one purpose and one target: a request proof
names the action and the arguments' SHA-256; a decision proof names the request ID and the same hash. Each proof
is used once (its `jti`).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .citations import check_hypothesis, is_cause

CATALOGUE = {
    "killswitch.trip": {"approvers": 0, "roles": [], "hypothesis": None, "note": "any person; never an agent"},
    "killswitch.restore": {"never": True, "note": "two people through the kill-switch runbook, never this gate"},
    "deploy.rollback": {"approvers": 2, "roles": ["platform-oncall", "tech-lead"], "hypothesis": "deploy",
                        "precondition": "deploy_in_window"},
    "db.failover": {"approvers": 2, "roles": ["platform-oncall", "tech-lead"], "hypothesis": "database"},
    "worker.restart": {"approvers": 1, "roles": ["platform-oncall", "tech-lead"], "hypothesis": "worker"},
    "signin.rate_limit": {"approvers": 1, "roles": ["security-oncall"], "hypothesis": "signin-attack"},
}
OVERRIDE = re.compile(r"^(?:INC|RLY)-\d+: .{20,}$")  # an incident or ticket ID, then a reason of 20+ characters


def narrow_networks(requested, flagged: set[str]) -> bool:
    """A sign-in limit may name only networks SD-002 flagged, each at least a /16 (IPv4) or /48 (IPv6)."""
    if not isinstance(requested, list) or not requested:
        return False
    for text in requested:
        try:
            net = ipaddress.ip_network(text, strict=False)
        except ValueError:
            return False
        if net.prefixlen < (16 if net.version == 4 else 48) or str(net) not in flagged:
            return False
    return True


def matches(kind: str, h: dict, args: dict, flagged: set[str] = frozenset()) -> bool:
    """Does hypothesis `h` justify this kind of action with these arguments? (provided)

    - deploy: a cause hypothesis whose cause is the deploy being rolled back, `event:<args["deploy"]>`.
    - database: a cause hypothesis whose cause is a database metric (`metric:db_...`).
    - worker: a cause hypothesis whose cause is a worker metric (`metric:worker_...`).
    - signin-attack: an attribution that cites detection alert SD-002 (many credentials from one network), for a
      request whose `args["networks"]` are all among the networks SD-002 flagged (`flagged`) and none wider
      than a /16 (IPv4) or /48 (IPv6) (`narrow_networks`).
    A hypothesis without a structured cause and effect justifies nothing else, whatever its claim's text says.
    """
    cause = h.get("cause") if is_cause(h) else None
    if kind == "deploy":
        return cause == f"event:{args.get('deploy')}"
    if kind == "database":
        return bool(cause) and cause.startswith("metric:db_")
    if kind == "worker":
        return bool(cause) and cause.startswith("metric:worker_")
    if kind == "signin-attack":
        return (any(c["ref"] == "alert:SD-002" for c in h.get("citations") or [])
                and narrow_networks(args.get("networks"), flagged))
    return False
PROOF_MAX_AGE_S = 300
REQUEST_TTL = timedelta(minutes=15)


class Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def args_sha256(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True).encode("utf-8")).hexdigest()


def _sign(people: dict, body: dict) -> str:
    return hmac.new(bytes.fromhex(people["key_hex"]), json.dumps(body, sort_keys=True).encode(), "sha256").hexdigest()


def make_proof(people: dict, sub: str, iat: datetime, **bind) -> dict:
    """A short-lived proof for `sub`, bound to one purpose and target, signed by the lab's issuer (provided).

    Request: make_proof(p, sub, t, purpose="request", action=..., args_sha256=...).
    Decision: make_proof(p, sub, t, purpose="decide", request_id=..., args_sha256=...).
    """
    body = {"sub": sub, "aud": people["audience"], "iss": people["issuer"],
            "iat": iat.strftime("%Y-%m-%dT%H:%M:%SZ"), **bind}
    body["jti"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    return {**body, "sig": _sign(people, body)}


@dataclass
class Request:
    request_id: str
    action: str
    args_sha256: str
    requester: str
    at: datetime
    expires: datetime
    because: str | None
    status: str = "pending"  # pending, approved, denied, expired, done
    approvals: list = field(default_factory=list)  # (person, at)


class Gate:
    def __init__(self, people: dict, deploys: list[datetime] = (), store=None, hypotheses: dict | None = None) -> None:
        """`store` and `hypotheses` (ID -> hypothesis) let the gate judge each `because` itself, as of the request."""
        self.people, self.deploys = people, list(deploys)
        self.store, self.hypotheses = store, dict(hypotheses or {})
        self.requests: dict[str, Request] = {}
        self.audit: list[dict] = []
        self.used: set[str] = set()

    def _record(self, at: datetime, action: str, by: str, outcome: str, code: str = "") -> None:
        self.audit.append({"at": at.strftime("%H:%M:%S"), "action": action, "by": by, "outcome": outcome,
                           "code": code})

    def refuse(self, at: datetime, action: str, by: str, code: str):
        self._record(at, action, by, "refused", code)
        raise Refused(code)

    def authenticate(self, proof: dict, at: datetime, expect: dict) -> str:
        """The identity a proof names (a person or a registered agent), if genuine, fresh, unused and for `expect`.

        Raises Refused: bad_proof, wrong_audience, stale_proof, unknown_identity, proof_not_for_this,
        proof_reused. Not audited here; the caller audits. A successful call uses the proof up.
        """
        body = {k: v for k, v in proof.items() if k != "sig"}
        if not hmac.compare_digest(_sign(self.people, body), str(proof.get("sig", ""))):
            raise Refused("bad_proof")
        if proof.get("aud") != self.people["audience"] or proof.get("iss") != self.people["issuer"]:
            raise Refused("wrong_audience")
        iat = datetime.strptime(proof["iat"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=at.tzinfo)
        if not timedelta(0) <= at - iat <= timedelta(seconds=PROOF_MAX_AGE_S):
            raise Refused("stale_proof")
        if proof["sub"] not in self.people["people"] and proof["sub"] not in self.people["agents"]:
            raise Refused("unknown_identity")
        if any(proof.get(k) != v for k, v in expect.items()):
            raise Refused("proof_not_for_this")
        if proof["jti"] in self.used:
            raise Refused("proof_reused")
        self.used.add(proof["jti"])
        return proof["sub"]

    def is_agent(self, sub: str) -> bool:
        return sub in self.people["agents"]

    def verdict(self, because: str | None, at: datetime) -> tuple[dict | None, str]:
        """The hypothesis and the citation check's verdict on it as of `at`, computed here, never taken from a caller."""
        h = self.hypotheses.get(because) if because else None
        if h is None or self.store is None or (h.get("made_at") and h["made_at"] > at):
            return None, "unknown"
        return h, check_hypothesis(h, self.store.view(at)).status

    def flagged_networks(self, at: datetime) -> set[str]:
        """The networks SD-002 had flagged by `at`, from the store's alerts."""
        if self.store is None:
            return set()
        return {a.group for a in self.store.alerts if a.rule == "SD-002" and a.at <= at and getattr(a, "group", "")}

    def request(self, action: str, args: dict, proof: dict, at: datetime, because: str | None = None,
                override: str = "") -> Request:
        """Record an authenticated request (provided). Refused, and audited:

        unknown_action; not_through_this_gate (restore); the proof's codes; agents_may_not_trip. For an action that
        needs a hypothesis, the gate judges `because` itself; it must be supported and must `match` the action.
        Otherwise an agent is refused (unsupported_hypothesis, or hypothesis_does_not_match_action), and a person
        is refused unless `override` names an incident or ticket and gives a reason (OVERRIDE); a person's override
        is audited as outcome "override". Then precondition_failed:no_deploy_in_2h.
        """
        claimed = str(proof.get("sub"))
        spec = CATALOGUE.get(action)
        if spec is None:
            self.refuse(at, action, claimed, "unknown_action")
        if spec.get("never"):
            self.refuse(at, action, claimed, "not_through_this_gate")
        sha = args_sha256(args)
        try:
            sub = self.authenticate(proof, at, {"purpose": "request", "action": action, "args_sha256": sha})
        except Refused as exc:
            self.refuse(at, action, f"unauthenticated:{claimed}", exc.code)
        if action == "killswitch.trip" and self.is_agent(sub):
            self.refuse(at, action, sub, "agents_may_not_trip")
        if spec.get("hypothesis"):
            h, status = self.verdict(because, at)
            problem = None
            if status != "supported":
                problem = "unsupported_hypothesis"
            elif not matches(spec["hypothesis"], h, args, self.flagged_networks(at)):
                problem = "hypothesis_does_not_match_action"
            if problem:
                if self.is_agent(sub):
                    self.refuse(at, action, sub, problem)
                if not OVERRIDE.match(override.strip()):
                    self.refuse(at, action, sub, "override_reason_required")
                self._record(at, action, sub, "override", f"{because}: {problem}; {override.strip()}")
        if spec.get("precondition") == "deploy_in_window" and not any(
                timedelta(0) <= at - d <= timedelta(hours=2) for d in self.deploys):
            self.refuse(at, action, sub, "precondition_failed:no_deploy_in_2h")
        rid = f"{action}#{len(self.requests) + 1}"
        req = Request(rid, action, sha, sub, at, at + REQUEST_TTL, because)
        if spec["approvers"] == 0:
            req.status = "approved"
        self.requests[rid] = req
        self._record(at, action, sub, "requested" if req.status == "pending" else "approved")
        return req

    def find(self, action: str) -> Request | None:
        found = [r for r in self.requests.values() if r.action == action]
        return found[-1] if found else None

    def decide(self, request_id: str, proof: dict, approve: bool, at: datetime) -> Request:
        """TODO 3. A decision on a request. Every refusal is audited (use `refuse`) and raises Refused.

        Check, in this order, auditing as `by` the proof's claimed `sub`, or "unauthenticated:<sub>" for proof
        failures: the request exists (no_such_request, with action request_id); it is pending (not_pending); it has
        not expired (expired: also set its status to "expired"); the proof (`authenticate`, expecting purpose
        "decide", this request_id and the request's args_sha256; refuse with its code); the decider is not an agent
        (agents_may_not_approve); the decider has one of the action's roles (wrong_role); has not already approved
        it (already_approved); and, for a one-person action, is not the requester (requester_may_not_approve).
        A denial sets status "denied", audited as outcome "denied". An approval is appended as (person, at) and
        audited as outcome "approval"; when the distinct approvers reach `approvers` and, for two-person actions,
        their roles cover every listed role, the status becomes "approved" (audited as outcome "approved").
        """
        raise NotImplementedError("TODO 3: decide")

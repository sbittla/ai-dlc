"""Agent identities and the short-lived tokens Relay issues to them (added in 4.23.0; ADR-020).

Every agent that calls Relay has an entry in the registry (`governance/agents.json`): an id, the
person accountable for it, the workload it runs as, and the scopes it may hold. No agent holds a
stored Relay credential. At run time the agent proves which workload it is, with a token from its
platform (GitHub Actions OIDC for CI jobs; a signed AWS identity request for ECS tasks), and
exchanges that proof for a Relay token that lasts at most 15 minutes and carries only the scopes
the run asked for, in the manner of OAuth 2.0 Token Exchange (RFC 8693).

What this module does not do: verify the platform's proof. `exchange` takes the claims that a
verifier has already checked (issuer, subject, audience). Verifying a GitHub OIDC token needs an
RS256 signature check against GitHub's published keys, which the standard library cannot do; the
verifier is a dependency with its own ADR and review (Chapter 13's rules), and is not part of
4.23.0. Tests use claims written by hand. Two properties of the proof are checked here all the same:
its audience must be Relay's (for a signed AWS request, the verifier takes it from a server-ID header
inside the signature, so a request signed for another service cannot be replayed to Relay), and it
must be fresh (`iat` no more than MAX_PROOF_AGE_SECONDS old).

Delegation is authenticated, not asserted. An agent whose registry entry says `delegation: required`
must present the person's own short-lived proof as well (RFC 8693's subject token, with the workload
as the actor), issued by the registry's `person_issuer` for Relay's audience. The person in the token
is the one recorded; a session cannot name anyone else. Whoever launches the session holds that proof
for its lifetime, which is why it must be short and audience-bound.

Verification stays inside the token service. Tokens are signed with a symmetric HMAC key, so any
component that verified them locally would also hold the key that mints them; consumers call
`verify` through the service instead. Asymmetric signatures are the later step (ADR-020).

Revocation is by epoch. Each agent has a counter; every token records the counter at issue; the
kill switch disables the agent and increments it, so every outstanding token fails on its next use,
wherever it was copied to. That holds only if every consumer calls `verify` on every request: a
cache of verification results delays revocation by the cache's lifetime (Lab 14.1's first drill).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

MAX_TTL_SECONDS = 900
MAX_PROOF_AGE_SECONDS = 300
TOKEN_PREFIX = "rla_"
AUDIENCE = "relay-token-exchange"
KINDS = frozenset({"ci-job", "ecs-task"})
DELEGATION = frozenset({"owner", "required"})

# Relay scopes no agent identity may ever hold, whatever the registry says (ADR-020): administering
# a workspace, managing agents or tokens, writing or deleting audit records, and break-glass access.
# The same rule on GitHub (no agent may approve or merge) is enforced by GitHub's permissions,
# branch protection and CODEOWNERS, and checked by tests/test_audit_registry_file.py.
FORBIDDEN_SCOPES = frozenset({"workspace:admin", "agents:manage", "tokens:manage", "audit:write", "audit:delete",
                              "break-glass:assume"})


class RegistryError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class TokenRejected(Exception):
    """A refused exchange or verification. `code` is stable and is what the audit trail records."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    kind: str
    owner: str
    issuer: str
    subject: str
    scopes: frozenset[str]
    max_ttl_seconds: int = MAX_TTL_SECONDS
    delegation: str = "owner"
    delegators: frozenset[str] = frozenset()
    cloud_role: str | None = None
    tool_limits: dict = field(default_factory=dict)
    github_app: str | None = None
    enabled: bool = True
    epoch: int = 1
    tripped_at: float | None = None


def validate(data: dict) -> list[str]:
    """Problems with a registry document, in a stable order. An empty list means it may be loaded."""
    problems: list[str] = []
    people = set(data.get("people", []))
    seen_ids: set[str] = set()
    seen_workloads: set[tuple[str, str]] = set()
    for a in data.get("agents", []):
        aid = a.get("agent_id", "?")
        if aid in seen_ids:
            problems.append(f"{aid}: duplicate agent_id")
        seen_ids.add(aid)
        if aid in people:
            problems.append(f"{aid}: an agent id may not be a person's name")
        if a.get("kind") not in KINDS:
            problems.append(f"{aid}: kind must be one of {', '.join(sorted(KINDS))}")
        if a.get("owner") not in people:
            problems.append(f"{aid}: owner {a.get('owner')!r} is not a person in the registry")
        workload = (a.get("issuer"), a.get("subject"))
        if not all(workload) or any("*" in str(w) for w in workload):
            problems.append(f"{aid}: issuer and subject must be exact, with no wildcard")
        elif workload in seen_workloads:
            problems.append(f"{aid}: workload already belongs to another agent (shared identity)")
        seen_workloads.add(workload)
        scopes = a.get("scopes", [])
        if not scopes:
            problems.append(f"{aid}: no scopes")
        problems += [f"{aid}: forbidden scope {s}" for s in sorted(set(scopes) & FORBIDDEN_SCOPES)]
        problems += [f"{aid}: wildcard scope {s}" for s in sorted(s for s in scopes if "*" in s)]
        ttl = a.get("max_ttl_seconds", MAX_TTL_SECONDS)
        if type(ttl) is not int or not 60 <= ttl <= MAX_TTL_SECONDS:
            problems.append(f"{aid}: max_ttl_seconds must be 60 to {MAX_TTL_SECONDS}")
        if a.get("delegation", "owner") not in DELEGATION:
            problems.append(f"{aid}: delegation must be owner or required")
        if a.get("delegation") == "required" and not set(a.get("delegators", [])) <= people:
            problems.append(f"{aid}: every delegator must be a person in the registry")
        if a.get("delegation") == "required" and not data.get("person_issuer"):
            problems.append(f"{aid}: delegation required, but the registry names no person_issuer")
    return problems


class AgentRegistry:
    """The registry in memory. Disabling an agent also increments its epoch."""

    def __init__(self, data: dict) -> None:
        problems = validate(data)
        if problems:
            raise RegistryError(problems)
        self.version = data.get("version")
        self.people = frozenset(data.get("people", []))
        self.person_issuer = data.get("person_issuer")
        self._agents = {a["agent_id"]: AgentIdentity(
            agent_id=a["agent_id"], kind=a["kind"], owner=a["owner"], issuer=a["issuer"], subject=a["subject"],
            scopes=frozenset(a["scopes"]), max_ttl_seconds=a.get("max_ttl_seconds", MAX_TTL_SECONDS),
            delegation=a.get("delegation", "owner"), delegators=frozenset(a.get("delegators", [])),
            cloud_role=a.get("cloud_role"), tool_limits=dict(a.get("tool_limits", {})),
            github_app=a.get("github_app"),
        ) for a in data.get("agents", [])}

    @classmethod
    def load(cls, path: Path) -> AgentRegistry:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def get(self, agent_id: str) -> AgentIdentity:
        return self._agents[agent_id]

    def agents(self) -> list[AgentIdentity]:
        return [self._agents[k] for k in sorted(self._agents)]

    def by_workload(self, issuer: str, subject: str) -> AgentIdentity | None:
        return next((a for a in self._agents.values() if (a.issuer, a.subject) == (issuer, subject)), None)

    def disable(self, agent_id: str, at: float | None = None) -> AgentIdentity:
        a = self._agents[agent_id]
        self._agents[agent_id] = replace(a, enabled=False, epoch=a.epoch + 1,
                                         tripped_at=time.time() if at is None else at)
        return self._agents[agent_id]

    def enable(self, agent_id: str, new_subject: str | None = None,
               new_cloud_role: str | None = None) -> AgentIdentity:
        """Re-enable without resetting the epoch: tokens issued before the kill switch stay dead.

        `new_subject` moves the agent to a new workload (for an ECS agent, a new role), so that proofs
        signed with credentials copied before the trip no longer match it.
        """
        a = self._agents[agent_id]
        if new_subject is not None:
            if any(o.agent_id != agent_id and (o.issuer, o.subject) == (a.issuer, new_subject)
                   for o in self._agents.values()):
                raise ValueError("the new subject belongs to another agent")
            a = replace(a, subject=new_subject, cloud_role=new_cloud_role or a.cloud_role)
        self._agents[agent_id] = replace(a, enabled=True)
        return self._agents[agent_id]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TokenService:
    """Issues and verifies Relay agent tokens, signed with HMAC-SHA256 under one service key."""

    def __init__(self, registry: AgentRegistry, key: bytes, clock: Callable[[], float] = time.time,
                 new_id: Callable[[], str] = lambda: secrets.token_hex(8)) -> None:
        if len(key) < 32:
            raise ValueError("the signing key must be at least 32 bytes")
        self.registry = registry
        self._key = key
        self.clock = clock
        self.new_id = new_id

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).digest())

    def _fresh(self, claims: dict) -> bool:
        iat = claims.get("iat")
        return isinstance(iat, (int, float)) and -60 <= self.clock() - iat <= MAX_PROOF_AGE_SECONDS

    def exchange(self, workload: dict, scopes: list[str], subject: dict | None = None,
                 ttl_seconds: int | None = None) -> tuple[str, dict]:
        """Exchange verified workload claims {iss, sub, aud, iat} for a token. Refusals, in check order:

        unknown_workload, wrong_audience, stale_proof (no `iat`, or older than MAX_PROOF_AGE_SECONDS),
        disabled, no_scope, forbidden_scope, scope_not_granted; then, for a `required` agent,
        delegation_required (no subject token), bad_subject_token (wrong issuer or audience, or stale),
        delegator_not_allowed (the person is not one of its delegators); for an `owner` agent,
        unexpected_subject (a subject token was sent). The lifetime is the smaller of `ttl_seconds` and
        the agent's maximum.
        """
        agent = self.registry.by_workload(workload.get("iss", ""), workload.get("sub", ""))
        if agent is None:
            raise TokenRejected("unknown_workload")
        if workload.get("aud") != AUDIENCE:
            raise TokenRejected("wrong_audience")
        if not self._fresh(workload):
            raise TokenRejected("stale_proof")
        if not agent.enabled:
            raise TokenRejected("disabled")
        wanted = set(scopes)
        if not wanted:
            raise TokenRejected("no_scope")
        if wanted & FORBIDDEN_SCOPES:
            raise TokenRejected("forbidden_scope")
        if not wanted <= agent.scopes:
            raise TokenRejected("scope_not_granted")
        if agent.delegation == "required":
            if subject is None:
                raise TokenRejected("delegation_required")
            if (subject.get("iss") != self.registry.person_issuer or subject.get("aud") != AUDIENCE
                    or not self._fresh(subject)):
                raise TokenRejected("bad_subject_token")
            on_behalf_of = subject.get("sub")
            if on_behalf_of not in agent.delegators:
                raise TokenRejected("delegator_not_allowed")
        else:
            if subject is not None:
                raise TokenRejected("unexpected_subject")
            on_behalf_of = None
        now = int(self.clock())
        ttl = min(ttl_seconds or agent.max_ttl_seconds, agent.max_ttl_seconds)
        claims = {"sub": agent.agent_id, "own": agent.owner, "obo": on_behalf_of or agent.owner,
                  "scp": sorted(wanted), "iat": now, "exp": now + ttl, "ep": agent.epoch, "jti": self.new_id()}
        payload = _b64(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return f"{TOKEN_PREFIX}{payload}.{self._sign(payload)}", claims

    def verify(self, token: str, scope: str | None = None) -> dict:
        """The token's claims if it may be used now (for `scope`, if given). Refusals, in check order:

        malformed, bad_signature, expired, unknown_agent, disabled, revoked (issued before the
        agent's current epoch), scope_missing.
        """
        if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX) or token.count(".") != 1:
            raise TokenRejected("malformed")
        payload, signature = token[len(TOKEN_PREFIX):].split(".")
        if not hmac.compare_digest(signature, self._sign(payload)):
            raise TokenRejected("bad_signature")
        try:
            claims = json.loads(_unb64(payload))
        except ValueError:
            raise TokenRejected("malformed") from None
        if self.clock() >= claims["exp"]:
            raise TokenRejected("expired")
        try:
            agent = self.registry.get(claims["sub"])
        except KeyError:
            raise TokenRejected("unknown_agent") from None
        if not agent.enabled:
            raise TokenRejected("disabled")
        if claims["ep"] != agent.epoch:
            raise TokenRejected("revoked")
        if scope is not None and scope not in claims["scp"]:
            raise TokenRejected("scope_missing")
        return claims

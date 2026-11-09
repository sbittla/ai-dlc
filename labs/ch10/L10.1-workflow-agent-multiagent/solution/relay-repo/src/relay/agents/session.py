"""An agent's own short-lived Relay token, refreshed as it runs (added in 4.24.0; ADR-025).

Each agent in a design runs under its own registered identity (ADR-020), never a shared one. The
session exchanges a fresh workload proof for a 15-minute token holding only the scopes the agent
declared for this run, and exchanges again when fewer than REFRESH_MARGIN_SECONDS remain. The token is
held in memory only; it is never written to the journal, a checkpoint or a log.

The boundary verifies the token on every tool call, with no cache. If the agent has been disabled by the
kill switch, verification fails on the next call and the run stops as `revoked` (ADR-022).
"""

from __future__ import annotations

from typing import Callable

from ..audit import TokenRejected, TokenService

REFRESH_MARGIN_SECONDS = 60
STOPPING = frozenset({"disabled", "revoked", "unknown_agent", "unknown_workload", "bad_signature",
                      "delegator_not_allowed", "bad_subject_token", "delegation_required"})


DELEGATION_CODES = frozenset({"bad_subject_token", "delegation_required"})


class AgentRevoked(Exception):
    """The agent may not act any more. `code` is the token service's refusal code; `status` is how the run ends."""

    status = "revoked"

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DelegationExpired(AgentRevoked):
    """The agent itself is fine, but it holds no fresh proof from the person it acts for. Its requester must
    resume the run with a new proof; nothing was revoked."""

    status = "delegation_expired"


def stopped(code: str) -> AgentRevoked:
    return DelegationExpired(code) if code in DELEGATION_CODES else AgentRevoked(code)


class AgentSession:
    def __init__(self, service: TokenService, agent_id: str, scopes: list[str],
                 prove: Callable[[], dict], subject: Callable[[], dict] | None = None) -> None:
        self.service = service
        self.agent_id = agent_id
        self.scopes = sorted(scopes)
        self._prove = prove
        self._subject = subject
        self._token: str | None = None
        self._claims: dict | None = None
        self.exchanges = 0

    @property
    def claims(self) -> dict | None:
        return self._claims

    @property
    def on_behalf_of(self) -> str | None:
        return self._claims["obo"] if self._claims else None

    def _exchange(self) -> None:
        try:
            self._token, self._claims = self.service.exchange(self._prove(), self.scopes,
                                                              self._subject() if self._subject else None)
        except TokenRejected as exc:
            raise stopped(exc.code) from None
        if self._claims["sub"] != self.agent_id:
            raise AgentRevoked("wrong_agent")
        self.exchanges += 1

    def verify(self, scope: str | None) -> dict:
        """Claims of a token valid now for `scope`, refreshing it first if it is about to expire."""
        if self._claims is None or self._claims["exp"] - self.service.clock() < REFRESH_MARGIN_SECONDS:
            self._exchange()
        try:
            return self.service.verify(self._token, scope)
        except TokenRejected as exc:
            if exc.code == "expired":
                self._exchange()
                return self.service.verify(self._token, scope)
            if exc.code in STOPPING:
                raise stopped(exc.code) from None
            raise

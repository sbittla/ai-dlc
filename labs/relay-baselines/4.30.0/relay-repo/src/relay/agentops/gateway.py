"""Agent tokens at Relay's HTTP service: verified on every request, and every request audited (4.30.0; ADR-051).

Chapter 14 built agent identities and 15-minute tokens (`rla_…`) and left two hooks for later: the service
must verify an agent's token on every request, with no cache, and write an audit-trail record for each one.
Both needed the registry's enabled flags and epochs in a shared database (`SharedRegistry`), so that a kill
switch tripped anywhere is refused here on the next request.

`AgentGateway` wraps Relay's WSGI application. A request whose bearer token starts with `rla_` is an agent's:

1. its route must be one agents may use (`AGENT_ROUTES`); anything else is 403 `route_not_for_agents`;
2. its token is verified by the token service for the route's scope, now (401 for a token that is malformed,
   badly signed, expired or for an unknown agent; 403 for a disabled or revoked agent or a missing scope);
3. it is rate limited per agent, with the service's own limiter;
4. the route runs as the agent, a Member-level reader limited by its scopes;
5. one audit record is written whatever happened, with the agent, its owner, the person it acts for and its
   token's ID, never the token itself.

Every other request goes to the application unchanged. In 4.30.0 agents may read one route: a task, with
scope `tasks:read:<team>`, where the team owns the task's project (`project_teams`).
"""

from __future__ import annotations

import json
import re
from typing import Callable, Iterable

from ..audit import AuditTrail, TokenRejected, TokenService
from ..models import User
from ..service.app import RelayApp
from ..service.responses import Response, error

TOKEN_PREFIX = "rla_"
TASK_PATH = re.compile(r"^/v1/projects/(\d+)/tasks/(\d+)$")
UNAUTHENTICATED = frozenset({"malformed", "bad_signature", "expired", "unknown_agent"})
_REASONS = {200: "OK", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
            429: "Too Many Requests", 500: "Internal Server Error"}


class AgentGateway:
    def __init__(self, app: RelayApp, tokens: TokenService, trail: AuditTrail, project_teams: dict[int, str],
                 clock: Callable[[], float] | None = None) -> None:
        self.app, self.tokens, self.trail = app, tokens, trail
        self.project_teams = dict(project_teams)
        self.clock = clock or app.clock

    def __call__(self, environ: dict, start_response) -> Iterable[bytes]:
        header = environ.get("HTTP_AUTHORIZATION", "")
        scheme, _, token = header.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token.startswith(TOKEN_PREFIX):
            return self.app(environ, start_response)
        try:
            resp = self.handle(environ, token)
        except Exception:  # noqa: BLE001 - never leak a traceback, never let an agent request skip its record
            resp = error(500, "internal error")
        payload = json.dumps(resp.body, sort_keys=True).encode("utf-8")
        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))]
        headers += sorted(resp.headers.items())
        start_response(f"{resp.status} {_REASONS.get(resp.status, '')}".rstrip(), headers)
        return [payload]

    def _route(self, method: str, path: str) -> tuple[str, str | None, Callable[[User], Response]] | None:
        if (m := TASK_PATH.match(path)) and method == "GET":
            pid, tid = int(m[1]), int(m[2])
            team = self.project_teams.get(pid)
            return (f"project:{pid}/task:{tid}", f"tasks:read:{team}" if team else None,
                    lambda user: self.app.get_task(user, pid, tid))
        return None

    def handle(self, environ: dict, token: str) -> Response:
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        route = self._route(method, path)
        if route is None:
            claims = self._claims_or_none(token)
            return self._done(claims, f"http.{method}", path[:80], 403, "route_not_for_agents")
        resource, scope, serve = route
        if scope is None:
            return self._done(self._claims_or_none(token), f"http.{method}", resource, 403, "no_team_for_project")
        try:
            claims = self.tokens.verify(token, scope)  # every request, no cache: a trip anywhere is seen here
        except TokenRejected as exc:
            status = 401 if exc.code in UNAUTHENTICATED else 403
            return self._done(None, f"http.{method}", resource, status, exc.code)
        allowed, retry_after = self.app.limiter.check(f"agent:{claims['sub']}", self.clock())
        if not allowed:
            return self._done(claims, f"http.{method}", resource, 429, "rate_limited",
                              headers={"Retry-After": str(retry_after)})
        agent = User(0, f"{claims['sub']}@agents.relay.invalid", claims["sub"], "Member", "UTC")
        resp = serve(agent)
        return self._done(claims, f"http.{method}", resource, resp.status, None, resp)

    @staticmethod
    def settings_problems(env) -> list[str]:
        """What is wrong with the agent-token settings; an empty list means none are set or all are usable."""
        if not env.get("RELAY_AGENT_TOKEN_KEY"):
            return []
        problems = [f"{name} is required with RELAY_AGENT_TOKEN_KEY" for name in
                    ("RELAY_AGENT_REGISTRY", "RELAY_AUDIT_TRAIL", "RELAY_PROJECT_TEAMS", "RELAY_DB_PATH")
                    if not env.get(name)]
        try:
            if len(bytes.fromhex(env["RELAY_AGENT_TOKEN_KEY"])) < 32:
                problems.append("RELAY_AGENT_TOKEN_KEY must be at least 32 bytes, in hex")
        except ValueError:
            problems.append("RELAY_AGENT_TOKEN_KEY must be hex")
        try:
            parse_project_teams(env.get("RELAY_PROJECT_TEAMS", ""))
        except ValueError as exc:
            problems.append(str(exc))
        return problems

    def _claims_or_none(self, token: str) -> dict | None:
        try:
            return self.tokens.verify(token)
        except TokenRejected:
            return None

    def _done(self, claims: dict | None, action: str, resource: str, status: int, code: str | None,
              resp: Response | None = None, headers: dict | None = None) -> Response:
        outcome = "ok" if status < 400 else ("refused" if status in (401, 403, 429) else "error")
        detail = {"status": status}
        if code:
            detail["code"] = code
        self.trail.append(agent_id=claims["sub"] if claims else None, owner=claims["own"] if claims else None,
                          on_behalf_of=claims["obo"] if claims else None,
                          credential=claims["jti"] if claims else None, action=action, resource=resource,
                          outcome=outcome, source="relay.service", detail=detail)
        if resp is not None:
            return resp
        return error(status, code or "error", **(headers or {}))


def parse_project_teams(text: str) -> dict[int, str]:
    """`10=platform,11=payments` -> {10: "platform", 11: "payments"}. Teams are lower-case words."""
    out: dict[int, str] = {}
    for part in (p.strip() for p in text.split(",") if p.strip()):
        pid, _, team = part.partition("=")
        if not pid.strip().isdigit() or not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", team.strip()):
            raise ValueError(f"RELAY_PROJECT_TEAMS: cannot read {part!r}; use 10=platform,11=payments")
        out[int(pid)] = team.strip()
    return out


def gateway_from_env(app: RelayApp, env) -> RelayApp | AgentGateway:
    """Wrap `app` in an AgentGateway when RELAY_AGENT_TOKEN_KEY is set; otherwise return it unchanged.

    Without the key, an agent token reaches the application, which does not know it and answers 401: the
    service fails closed. With the key, every other setting must be present and usable, or this raises
    ValueError and the process does not start half-configured.
    """
    if not env.get("RELAY_AGENT_TOKEN_KEY"):
        return app
    problems = AgentGateway.settings_problems(env)
    if problems:
        raise ValueError("; ".join(problems))
    from .registry_state import SharedRegistry
    registry = SharedRegistry.open(env["RELAY_AGENT_REGISTRY"], env["RELAY_DB_PATH"])
    tokens = TokenService(registry, bytes.fromhex(env["RELAY_AGENT_TOKEN_KEY"]))
    return AgentGateway(app, tokens, AuditTrail(env["RELAY_AUDIT_TRAIL"]),
                        parse_project_teams(env["RELAY_PROJECT_TEAMS"]))

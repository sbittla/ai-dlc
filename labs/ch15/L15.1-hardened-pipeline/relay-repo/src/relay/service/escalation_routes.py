"""HTTP routes for escalation rules and a task's escalation (ADR-009, ADR-016; spec ESC-SPEC-1 1.2.0, B7 and B8).

    GET  /v1/projects/{pid}/escalation-rules              the project's rules
    GET  /v1/projects/{pid}/escalation-rules/{rid}        one rule
    PUT  /v1/projects/{pid}/escalation-rules/{rid}        create or replace a rule (Owner, Admin)
    DELETE /v1/projects/{pid}/escalation-rules/{rid}      delete a rule (Owner, Admin; 4.22.0)
    GET  /v1/projects/{pid}/tasks/{tid}/escalation        the task's escalation panel
    POST /v1/projects/{pid}/tasks/{tid}/priority          a person sets the priority
    POST /v1/projects/{pid}/tasks/{tid}/acknowledge       a person acknowledges the task

The contract is `specs/001-escalation-rules/contracts/escalation-api.openapi.json`.
Every rule change is checked on the server twice: against the JSON Schema
contract, then by `validate_rule` (SEC-01, SEC-02). Every refusal of a rule
change is audited. Error bodies name the fields that failed, never their values.
A project the caller cannot view answers 404, like one that does not exist, so
a Guest cannot discover other projects' IDs; 403 means a visible project whose
action the caller's role does not allow.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..escalation import (EscalationStore, RuleDeleted, RuleIdInUse, RuleNotFound, RuleRejected, acknowledge,
                          delete_rule, escalation_view, notice_recipients, refuse, rule_from_document, rules_for,
                          save_rule, set_priority, to_document, to_rule_document, validate)
from .responses import Response, error, read_json

CONTRACT_PATH = (Path(__file__).resolve().parents[3] / "specs" / "001-escalation-rules" / "contracts"
                 / "escalation-rules.schema.json")
RULE_DEPTH = 6  # a rule document nests six levels: rule, steps, step, targets, target
RULES_PATH = re.compile(r"^/v1/projects/(\d+)/escalation-rules$")
RULE_PATH = re.compile(r"^/v1/projects/(\d+)/escalation-rules/([A-Za-z0-9_-]{1,64})$")
TASK_ACTION_PATH = re.compile(r"^/v1/projects/(\d+)/tasks/(\d+)/(escalation|priority|acknowledge)$")
ROUTES = (  # (method, path template), exactly as the OpenAPI contract names them
    ("GET", "/v1/projects/{pid}/escalation-rules"),
    ("GET", "/v1/projects/{pid}/escalation-rules/{rid}"),
    ("PUT", "/v1/projects/{pid}/escalation-rules/{rid}"),
    ("DELETE", "/v1/projects/{pid}/escalation-rules/{rid}"),
    ("GET", "/v1/projects/{pid}/tasks/{tid}/escalation"),
    ("POST", "/v1/projects/{pid}/tasks/{tid}/priority"),
    ("POST", "/v1/projects/{pid}/tasks/{tid}/acknowledge"),
)
EDITORS = ("Owner", "Admin")
VIEW_RULES = ("Owner", "Admin", "Member")  # D2: Members see the rules for their projects; Guests do not


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _paths(problems: list[str]) -> list[str]:
    """'$.steps[0].targets[0]: expected integer, got str' -> '$.steps[0].targets[0]'. Values are never echoed."""
    return sorted({p.split(": ", 1)[0] for p in problems})


class EscalationRoutes:
    """Route handlers, called by RelayApp after authentication and rate limiting."""

    def __init__(self, app, store: EscalationStore, contract: dict | None = None, link_base: str | None = None) -> None:
        self.app, self.store = app, store
        self.contract = contract if contract is not None else load_contract()
        # The web address in rule notices. Deployments pass their own (ADR-016); the default names the workspace.
        self.link_base = link_base if link_base is not None else f"https://relay.example/{app.directory.workspace}"

    def matches(self, path: str) -> bool:
        return bool(RULES_PATH.match(path) or RULE_PATH.match(path) or TASK_ACTION_PATH.match(path))

    def handle(self, user, method: str, path: str, environ: dict, now: float):
        at = datetime.fromtimestamp(now, tz=timezone.utc)
        if (m := RULES_PATH.match(path)):
            if method != "GET":
                return error(405, "method not allowed")
            return self.list_rules(user, int(m[1]))
        if (m := RULE_PATH.match(path)):
            if method == "GET":
                return self.get_rule(user, int(m[1]), m[2])
            if method == "PUT":
                return self.put_rule(user, int(m[1]), m[2], environ, at)
            if method == "DELETE":
                return self.delete_rule(user, int(m[1]), m[2], at)
            return error(405, "method not allowed")
        m = TASK_ACTION_PATH.match(path)
        pid, tid, action = int(m[1]), int(m[2]), m[3]
        expected = "GET" if action == "escalation" else "POST"
        if method != expected:
            return error(405, "method not allowed")
        return self.task_action(user, pid, tid, action, environ, at)

    # ------------------------------------------------------------------ rules

    def _project(self, user, project_id: int, roles: tuple[str, ...]):
        project = self.app.directory.projects.get(project_id)
        if project is None:
            return None, error(404, "not found")
        if not self.app.can_view(user, project):
            return None, error(404, "not found")  # do not reveal that a project the caller cannot view exists
        if user.role not in roles:
            return None, error(403, "forbidden")
        return project, None

    def list_rules(self, user, project_id: int):
        project, problem = self._project(user, project_id, VIEW_RULES)
        if problem:
            return problem
        return Response(200, {"rules": [to_rule_document(r) for r in rules_for(self.store, project.id)]})

    def get_rule(self, user, project_id: int, rule_id: str):
        project, problem = self._project(user, project_id, VIEW_RULES)
        if problem:
            return problem
        document = self.store.rule_document(rule_id)
        if document is None or document["project_id"] != project.id:
            return error(404, "not found")
        return Response(200, document)

    def put_rule(self, user, project_id: int, rule_id: str, environ: dict, at: datetime):
        project = self.app.directory.projects.get(project_id)
        if project is None or not self.app.can_view(user, project):
            return error(404, "not found")  # 4.22.0: an unviewable project looks absent, and nothing is audited
        if user.role not in EDITORS:  # SEC-01, ESC-AC21: refused before the body is read
            refuse(self.store, user, rule_id, "not_rule_editor", at)
            return error(403, "forbidden: only Owners and Admins change escalation rules")
        body, problem = read_json(environ, max_depth=RULE_DEPTH)
        if problem is not None:
            refuse(self.store, user, rule_id, "invalid_document", at, [f"HTTP {problem.status}"])
            return problem
        errors = validate(body, {"$ref": "#/$defs/Rule"}, self.contract)
        if not errors and (body["rule_id"] != rule_id or body["project_id"] != project_id):
            errors = ["$.rule_id or $.project_id: must equal the path"]
        if errors:  # ESC-AC24: an address target fails here, and the refusal is audited
            refuse(self.store, user, rule_id, "invalid_document", at, _paths(errors))
            return Response(400, {"error": "the rule does not match the contract", "problems": _paths(errors)})
        rule = rule_from_document(body)
        try:
            created = save_rule(self.store, rule, user, project, self.app.directory.users, at, self.link_base)
        except RuleRejected as refused:
            return Response(422, to_document(refused.rejection))
        except RuleIdInUse:
            return error(409, "rule ID already used by a rule in another project, or by a deleted rule")
        return Response(201 if created else 200, to_rule_document(rule),
                        {"Location": f"/v1/projects/{project_id}/escalation-rules/{rule_id}"})

    def delete_rule(self, user, project_id: int, rule_id: str, at: datetime):
        """B8: checked in the order authentication, rate limit, project (404 if absent or not viewable, not audited),
        role (403, audited), then the rule (404)."""
        project = self.app.directory.projects.get(project_id)
        if project is None or not self.app.can_view(user, project):
            return error(404, "not found")
        if user.role not in EDITORS:  # as for PUT: refused and audited before the rule is looked up
            refuse(self.store, user, rule_id, "not_rule_editor", at)
            return error(403, "forbidden: only Owners and Admins delete escalation rules")
        document = self.store.rule_document(rule_id)
        if document is None or document["project_id"] != project.id:
            return error(404, "not found")
        users = self.app.directory.users
        try:
            rule = delete_rule(self.store, rule_id, user, project, users, at, self.link_base)
        except RuleRejected:
            return error(403, "forbidden: only Owners and Admins delete escalation rules")
        except RuleNotFound:
            return error(404, "not found")
        notices = len(notice_recipients(users)) if rule.priority == "P1" else 0
        return Response(200, to_document(RuleDeleted(rule_id, at, notices)))

    # ------------------------------------------------------------------ a task's escalation

    def task_action(self, user, project_id: int, task_id: int, action: str, environ: dict, at: datetime):
        project = self.app.directory.projects.get(project_id)
        if project is None:
            return error(404, "not found")
        try:
            task = self.app.tasks.get(task_id)
        except KeyError:
            return error(404, "not found")
        if task.project_id != project.id or not self.app.can_view(user, project):
            return error(404, "not found")  # an unviewable project's tasks look like no tasks at all
        try:
            if action == "priority":
                body, problem = read_json(environ)
                if problem is not None:
                    return problem
                if not isinstance(body, dict) or set(body) != {"priority"} or not isinstance(body["priority"], str):
                    return error(400, 'body must be {"priority": "P1" | "P2" | "P3" | "P4"}')
                set_priority(self.store, task, project, user, body["priority"], at)
            elif action == "acknowledge":
                acknowledge(self.store, task, project, user, at)
            return Response(200, escalation_view(self.store, task, project, user))
        except PermissionError:
            return error(403, "forbidden")
        except ValueError:
            return error(400, 'body must be {"priority": "P1" | "P2" | "P3" | "P4"}')

"""Shared helpers for the service's escalation tests: a demo app, a WSGI caller and the refusal matrix.

Demo users (relay.service.directory): 1 Olu (Owner), 2 Ada (Admin), 3 Mei (Member), 4 Gil (Guest,
invited to project 10 only). Projects: 10 Rotterdam, 11 Hamburg.
"""

import io
import json
from datetime import date

from relay.escalation import EscalationStore
from relay.models import Task
from relay.service import RelayApp, demo_directory
from relay.store import TaskStore
from relay.worker import TriageQueue

T0 = 1_795_487_400.0  # 2026-11-24T02:30:00Z

RULE = {"rule_id": "R-ROT-P1", "project_id": 10, "priority": "P1", "name": "Rotterdam night P1",
        "steps": [{"number": 1, "delay_minutes": 10, "targets": [4]},
                  {"number": 2, "delay_minutes": 20, "targets": [2]}]}
HAMBURG_RULE = dict(RULE, rule_id="R-HAM-P1", project_id=11, steps=[{"number": 1, "delay_minutes": 10, "targets": [2]}])


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def make_app():
    tasks = TaskStore(":memory:")
    tasks.add(Task(100, 10, "Scanner gateway offline", "open", date(2026, 11, 20), 3))
    tasks.add(Task(102, 11, "Quarterly stock count", "done", None, 2))
    store = EscalationStore()
    app = RelayApp(demo_directory(), tasks, TriageQueue(":memory:"), clock=Clock(T0), escalation=store)
    return app, store


def call(app, method, path, token=None, body=None, raw=None, length=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    has_body = body is not None or raw is not None
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO(data),
               "CONTENT_LENGTH": length if length is not None else (str(len(data)) if has_body else "")}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    seen = {}

    def start_response(status, headers):
        seen["status"], seen["headers"] = int(status.split()[0]), dict(headers)

    payload = b"".join(app(environ, start_response))
    return seen["status"], seen["headers"], json.loads(payload)


RULES = "/v1/projects/10/escalation-rules"
ONE_RULE = "/v1/projects/10/escalation-rules/R-ROT-P1"
HAMBURG_RULES = "/v1/projects/11/escalation-rules"
TASK = "/v1/projects/10/tasks/100"
HAMBURG_TASK = "/v1/projects/11/tasks/102"
TOO_LARGE = b"{" + b" " * 16_400 + b"}"

# The refusal matrix (SEC-07): for every route, who is refused and how. Each row is
# (route template, method, path, token, body or raw bytes, expected status, why).
MATRIX = [
    ("/v1/projects/{pid}/escalation-rules", "GET", RULES, None, None, 401, "no token"),
    ("/v1/projects/{pid}/escalation-rules", "GET", RULES, "demo-guest", None, 403, "Guests do not see rules (D2)"),
    ("/v1/projects/{pid}/escalation-rules", "GET", "/v1/projects/99/escalation-rules", "demo-owner", None, 404,
     "unknown project"),
    ("/v1/projects/{pid}/escalation-rules", "POST", RULES, "demo-admin", RULE, 405, "wrong method"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "GET", ONE_RULE, None, None, 401, "no token"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "GET", ONE_RULE, "demo-guest", None, 403, "Guest"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "GET", "/v1/projects/10/escalation-rules/R-NONE", "demo-member",
     None, 404, "unknown rule"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, None, RULE, 401, "no token"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-member", RULE, 403, "Member (ESC-AC21)"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-guest", RULE, 403, "Guest"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", "/v1/projects/99/escalation-rules/R-ROT-P1", "demo-admin",
     RULE, 404, "unknown project"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-admin", b"{not json", 400, "bad JSON"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-admin", TOO_LARGE, 413, "too large"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-admin",
     dict(RULE, steps=[{"number": 1, "delay_minutes": 10, "targets": ["ops@outside.example"]}]), 400,
     "address target (ESC-AC24)"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-admin", dict(RULE, rule_id="R-OTHER"), 400,
     "body and path disagree"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "PUT", ONE_RULE, "demo-admin",
     dict(RULE, steps=[{"number": 1, "delay_minutes": 10, "targets": [99]}]), 422, "target not in workspace"),
    ("/v1/projects/{pid}/escalation-rules/{rid}", "DELETE", ONE_RULE, "demo-admin", None, 405, "no delete route"),
    ("/v1/projects/{pid}/tasks/{tid}/escalation", "GET", TASK + "/escalation", None, None, 401, "no token"),
    ("/v1/projects/{pid}/escalation-rules", "GET", HAMBURG_RULES, "demo-guest", None, 404,
     "Guest not invited to Hamburg: the project looks absent"),
    ("/v1/projects/{pid}/tasks/{tid}/escalation", "GET", HAMBURG_TASK + "/escalation", "demo-guest", None, 404,
     "Guest not invited to Hamburg: the task looks absent"),
    ("/v1/projects/{pid}/tasks/{tid}/escalation", "GET", "/v1/projects/10/tasks/102/escalation", "demo-owner",
     None, 404, "task in another project"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", TASK + "/priority", None, {"priority": "P1"}, 401,
     "no token"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", TASK + "/priority", "demo-guest", {"priority": "P1"}, 403,
     "Guests cannot set priorities (ESC-R01)"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", HAMBURG_TASK + "/priority", "demo-guest",
     {"priority": "P1"}, 404, "not invited: the task looks absent"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", "/v1/projects/10/tasks/999/priority", "demo-member",
     {"priority": "P1"}, 404, "unknown task"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", TASK + "/priority", "demo-member", {"priority": "urgent"},
     400, "unknown priority"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", TASK + "/priority", "demo-member",
     {"priority": "P1", "suggested": True}, 400, "extra field"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "POST", TASK + "/priority", "demo-member", TOO_LARGE, 413,
     "too large"),
    ("/v1/projects/{pid}/tasks/{tid}/priority", "GET", TASK + "/priority", "demo-member", None, 405,
     "wrong method"),
    ("/v1/projects/{pid}/tasks/{tid}/acknowledge", "POST", TASK + "/acknowledge", None, None, 401, "no token"),
    ("/v1/projects/{pid}/tasks/{tid}/acknowledge", "POST", HAMBURG_TASK + "/acknowledge", "demo-guest", None, 404,
     "not invited: the task looks absent"),
    ("/v1/projects/{pid}/tasks/{tid}/acknowledge", "POST", "/v1/projects/99/tasks/100/acknowledge", "demo-owner",
     None, 404, "unknown project"),
]

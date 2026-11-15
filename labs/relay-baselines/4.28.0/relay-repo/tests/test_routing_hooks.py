"""ADR-043's hooks on the real service and worker (tests/routing_hooks.py; merged into canonical 4.28.0)."""

import inspect
import io
import json

from routing_hooks import HOOK_LINES, MeteredTriage, QuotaRelayApp
from service_helpers import Clock

from relay.routing import QuotaLimits, SpendQuota
from relay.service import RelayApp, demo_directory
from relay.store import TaskStore
from relay.worker import TriageQueue, Worker
from relay.worker.triage import SimulatedTriage

T0 = 1_802_390_400.0 + 9 * 3600  # 2027-02-12T09:00:00Z


def body_lines(fn):
    return inspect.getsource(fn).splitlines()[1:]


def test_the_service_hook_is_the_current_method_plus_the_hook():
    ours = body_lines(QuotaRelayApp.create_job)
    assert sum("# HOOK" in line for line in ours) == HOOK_LINES
    assert [line for line in ours if "# HOOK" not in line] == body_lines(RelayApp.create_job)


def service(tmp_path, user_limit):
    quota = SpendQuota(str(tmp_path / "q.db"), QuotaLimits({"user": user_limit, "workspace": 1.0}))
    app = QuotaRelayApp(demo_directory(), TaskStore(), TriageQueue(), clock=Clock(T0), quota=quota,
                        triage_estimate_usd=0.004)
    return app, quota


def test_a_user_past_their_triage_quota_gets_429_and_others_do_not(tmp_path):
    app, quota = service(tmp_path, user_limit=0.01)
    statuses = [post_with_key(app, "demo-member", f"key-{i:05d}")[0] for i in range(3)]
    assert statuses == [202, 202, 429]
    status, headers, _ = post_with_key(app, "demo-member", "key-00000")  # a replay is not charged again
    assert status == 202 and headers.get("Idempotent-Replayed") == "true"
    assert post_with_key(app, "demo-admin", "key-admin-1")[0] == 202
    assert quota.refusals() == [("job:workspace:ws-demo:key-00002", "user:3")]


def post_with_key(app, token, key):
    data = json.dumps({"text": "The export button returns a 500 error."}).encode()
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/triage-jobs", "wsgi.input": io.BytesIO(data),
               "CONTENT_LENGTH": str(len(data)), "HTTP_AUTHORIZATION": f"Bearer {token}",
               "HTTP_IDEMPOTENCY_KEY": key}
    seen = {}

    def start_response(status, headers):
        seen["status"], seen["headers"] = int(status.split()[0]), dict(headers)

    payload = b"".join(app(environ, start_response))
    return seen["status"], seen["headers"], json.loads(payload)


def test_the_429_names_no_ticket_text_and_says_when_to_retry(tmp_path):
    app, _ = service(tmp_path, user_limit=0.001)
    status, headers, body = post_with_key(app, "demo-member", "key-00009")
    assert status == 429 and body == {"error": "triage spend quota reached"}
    assert headers["Retry-After"] == str(15 * 3600)


def test_a_spent_agent_quota_sends_jobs_to_a_person_never_to_a_guess(tmp_path):
    clock = Clock(T0)
    queue = TriageQueue(str(tmp_path / "relay.db"))
    for i in range(6):
        queue.enqueue("ws-1", f"job-key-{i}", f"Ticket {i}: the export button returns a 500 error.", T0)
    quota = SpendQuota(str(tmp_path / "relay.db"), QuotaLimits({"agent": 0.0060, "feature": 1.0}))
    metered = MeteredTriage(SimulatedTriage(unavailable_rate=0.0, invalid_rate=0.0), quota, prompt_chars=1800,
                            max_output_tokens=64, clock=clock)
    worker = Worker(queue, metered, clock=clock)
    for _ in range(40):
        worker.run_once()
        clock.t += 15.0
    counts = queue.counts()
    assert counts["done"] >= 1 and counts["needs_human"] >= 1 and counts["queued"] + counts["running"] == 0
    reasons = {queue.get(j).last_error for j in range(1, 7) if queue.get(j).status == "needs_human"}
    assert reasons == {"quota"}
    assert 0 < quota.spent("agent:triage-worker", T0) <= 0.0060
    assert metered.refused >= 3


def test_identical_ticket_texts_are_each_charged(tmp_path):
    """Must-fix (review round 1): a ref built from the text made a repeated text a free replay."""
    clock = Clock(T0)
    queue = TriageQueue(str(tmp_path / "relay.db"))
    for i in range(30):
        queue.enqueue("ws-1", f"same-text-{i:03d}", "How do I reset my password?", T0)
    quota = SpendQuota(str(tmp_path / "relay.db"), QuotaLimits({"agent": 0.0060, "feature": 1.0}))
    metered = MeteredTriage(SimulatedTriage(unavailable_rate=0.0, invalid_rate=0.0), quota, prompt_chars=1800,
                            max_output_tokens=64, clock=clock)
    worker = Worker(queue, metered, clock=clock)
    for _ in range(200):
        worker.run_once()
        clock.t += 15.0
    settled = quota.conn.execute("SELECT COUNT(*), SUM(usd) FROM spend_events WHERE outcome = 'settled'").fetchone()
    assert queue.counts()["done"] == settled[0] < 30                 # only the calls the quota allowed ran
    assert quota.spent("agent:triage-worker", T0) == round(settled[1], 9) <= 0.0060
    assert metered.refused > 0

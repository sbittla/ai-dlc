"""Alert delivery to the paging provider (added in 4.27.0; ADR-038).

The monitor decides what to page; this module sends it. It is in `relay.service` because only the service's
packages may make network calls (AR4), and it reaches the provider through the egress proxy like any other
outbound call. The provider is not named here: it is any service with an HTTPS events API that accepts a JSON
event with a routing key per receiver and a deduplication key, which most paging services offer.

- HTTPS only; the URL and the routing keys come from configuration (the keys are Restricted secrets).
- The event carries the alert's ID (the deduplication key), rule, severity, summary and evidence references,
  never telemetry values themselves: the summary was built from rule IDs, counts and thresholds.
- Grouping: within `group_minutes` of a page, a repeat alert for the same rule and receiver reuses its
  deduplication key, so the provider folds it into the open page. The monitor is a one-shot command run every
  minute, so the open keys are kept in `state_path` on the monitor's volume between runs. Escalation after 10
  and 20 minutes is configured in the provider's escalation policy, not here.
- A failed send is retried twice, then recorded in `failed` and written to the monitor's log. Nothing here
  notices a monitor that stops running; that needs a dead man's switch outside Relay (ADR-038, open item).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..telemetry.alerting import AlertRecord


@dataclass
class PagerClient:
    url: str
    routing_keys: dict[str, str] = field(repr=False)
    opener: object = None  # urllib.request.urlopen, or a fake in tests
    timeout_s: float = 5.0
    retries: int = 2
    group_minutes: int = 0  # reuse an open page's deduplication key for repeats of its rule (routing "grouping")
    sent: list = field(default_factory=list)
    open_keys: dict = field(default_factory=dict)  # (rule, receiver) -> (dedup key, first sent)
    failed: list = field(default_factory=list)
    state_path: str | None = None  # where the open keys survive between one-shot monitor runs

    def __post_init__(self) -> None:
        if not self.url.startswith("https://"):
            raise ValueError("the paging endpoint must be https://")
        self.opener = self.opener or urllib.request.urlopen
        if self.state_path and Path(self.state_path).exists():
            saved = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
            self.open_keys = {tuple(k.split("|", 1)): (v[0], datetime.fromisoformat(v[1])) for k, v in saved.items()}

    def _save(self) -> None:
        if self.state_path:
            data = {f"{r}|{rc}": [key, at.isoformat()] for (r, rc), (key, at) in self.open_keys.items()}
            Path(self.state_path).write_text(json.dumps(data, sort_keys=True), encoding="utf-8")

    def _dedup_key(self, alert: AlertRecord, receiver: str) -> str:
        key = (alert.rule, receiver)
        open_ = self.open_keys.get(key)
        if self.group_minutes and open_ and (alert.at - open_[1]).total_seconds() <= self.group_minutes * 60:
            return open_[0]
        self.open_keys[key] = (alert.alert_id, alert.at)
        self._save()
        return alert.alert_id

    def _event(self, alert: AlertRecord, receiver: str, action: str) -> dict:
        return {"routing_key": self.routing_keys[receiver], "event_action": action,
                "dedup_key": self._dedup_key(alert, receiver),
                "payload": {"summary": alert.summary[:1024], "source": "relay-monitor", "severity": alert.severity,
                            "timestamp": alert.at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "custom_details": {"rule": alert.rule, "category": alert.category,
                                               "evidence": list(alert.evidence)}}}

    def _post(self, body: dict) -> bool:
        data = json.dumps(body, sort_keys=True).encode("utf-8")
        for _ in range(self.retries + 1):
            req = urllib.request.Request(self.url, data=data, method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with self.opener(req, timeout=self.timeout_s) as resp:
                    if 200 <= resp.status < 300:
                        return True
            except OSError:
                continue
        return False

    def page(self, alert: AlertRecord, receiver: str, at: datetime) -> bool:
        ok = self._post(self._event(alert, receiver, "trigger"))
        (self.sent if ok else self.failed).append((at, receiver, alert.alert_id))
        return ok

    def ticket(self, alert: AlertRecord, receiver: str, at: datetime) -> bool:
        return self.page(alert, receiver, at)  # the provider's low-urgency route; the receiver's key decides

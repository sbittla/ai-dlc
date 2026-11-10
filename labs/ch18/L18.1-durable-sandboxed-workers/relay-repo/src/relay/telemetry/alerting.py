"""Alert rules, routing, paging with escalation, and the switch that turns automation off (4.27.0; ADR-038).

Three kinds of alert reach this module: SLO burn-rate episodes (`relay.telemetry.slo`), detection alerts
(`relay.telemetry.detection`) and operational threshold rules (`infra/monitoring/alerts.json`, AL-001 to
AL-008). Each becomes an `AlertRecord` with the evidence that fired it, and `Router` delivers it as
`infra/monitoring/routing.json` says: a page, a ticket, or an automated action.

Paging follows Relay's on-call policy: a page goes to the on-call engineer at once, escalates to the
secondary after 10 minutes without an acknowledgement and to the engineering manager after 20. Security
pages also notify the security lead, who must hear of a security incident within an hour.

Automation is limited to tripping an agent's kill switch, and only for the rules Chapter 14 allows
(DR-001, DR-003). It obeys its own off switch (`automation_enabled`, from `RELAY_AUTOMATION`) and a rate limit,
and it needs a `trip` function; when any of these stops it, the action becomes a page asking a person to decide,
recorded as `automation-suppressed` or `automation-unavailable`. Nothing in this module restores anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    rule: str
    at: datetime
    severity: str   # page or ticket (detection's high and medium map to page)
    category: str   # reliability or security
    summary: str
    evidence: tuple[str, ...] = ()
    group: str = ""


def from_detection(alert, category: str = "security") -> AlertRecord:
    """A detection alert (relay.telemetry.detection.Alert) as a routable record; high and medium page."""
    severity = "page" if alert.severity in ("high", "medium", "page") else "ticket"
    stamp = alert.alert_at.strftime("%Y%m%dT%H%M")
    return AlertRecord(f"{alert.rule}:{stamp}:{alert.group}", alert.rule, alert.alert_at, severity, category,
                       f"{alert.rule} for {alert.group}: {alert.value} over {alert.threshold}", alert.evidence,
                       alert.group)


def from_episode(slo_id: str, episode, minute_time, category: str = "reliability") -> AlertRecord:
    """An SLO burn-rate episode (relay.telemetry.slo.Episode) as a routable record, at its first minute."""
    at = minute_time(episode.start)
    return AlertRecord(f"{slo_id}:{episode.action}:{at.strftime('%Y%m%dT%H%M')}", slo_id, at, episode.action,
                       category, f"{slo_id} burning its error budget (policy rows {list(episode.rows)})",
                       (f"slo:{slo_id}@{at.strftime('%Y-%m-%dT%H:%M:%SZ')}",))


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _compare(value: float, op: str, threshold: float) -> bool:
    return {">": value > threshold, ">=": value >= threshold, "<": value < threshold}[op]


def operational_alerts(rules: dict, values: dict, at: datetime) -> list[AlertRecord]:
    """AL rules over a snapshot of metric values. A value may be a number, or a dict of group -> number."""
    out = []
    for rule in rules["rules"]:
        value = values.get(rule["metric"])
        if value is None:
            continue
        groups = value if isinstance(value, dict) else {"": value}
        for group, v in sorted(groups.items()):
            if _compare(v, rule["op"], rule["threshold"]):
                suffix = f" ({group})" if group else ""
                out.append(AlertRecord(f"{rule['id']}:{at.strftime('%Y%m%dT%H%M')}{':' + group if group else ''}",
                                       rule["id"], at, rule["severity"], rule["category"],
                                       f"{rule['title']}{suffix}: {rule['metric']} = {v:g}",
                                       (f"metric:{rule['metric']}{'{' + group + '}' if group else ''}@"
                                        f"{at.strftime('%Y-%m-%dT%H:%M:%SZ')}",), group))
    return out


@dataclass
class Page:
    alert: AlertRecord
    receiver: str
    sent_at: datetime
    acked_at: datetime | None = None
    acked_by: str | None = None
    escalations: list = field(default_factory=list)  # (at, to)
    grouped: list = field(default_factory=list)  # IDs of later alerts for the same rule, folded into this page


class Pager:
    """A simulated pager: pages, acknowledgements, timed escalation and grouping (labs and drills).

    With `group_minutes`, a new alert for the same rule and receiver within that many minutes of an open page
    is folded into it rather than paging again, as paging services group alerts (`routing.json`, "grouping").
    """

    def __init__(self, receivers: dict, group_minutes: int = 0) -> None:
        self.receivers, self.group_minutes = receivers, group_minutes
        self.pages: list[Page] = []
        self.notifications: list[tuple[datetime, str, str]] = []  # (at, to, alert_id)
        self.tickets: list[tuple[datetime, str, str]] = []

    def page(self, alert: AlertRecord, receiver: str, at: datetime) -> Page:
        if self.group_minutes:
            for open_page in reversed(self.pages):
                if (open_page.alert.rule == alert.rule and open_page.receiver == receiver
                        and at - open_page.sent_at <= timedelta(minutes=self.group_minutes)):
                    open_page.grouped.append(alert.alert_id)
                    return open_page
        p = Page(alert, receiver, at)
        self.pages.append(p)
        for to, within in self.receivers[receiver].get("notify", {}).items():
            self.notifications.append((at, to, alert.alert_id))  # sent at once; `within` is the deadline
        return p

    def ticket(self, alert: AlertRecord, receiver: str, at: datetime) -> None:
        self.tickets.append((at, receiver, alert.alert_id))

    def ack(self, alert_id: str, by: str, at: datetime) -> bool:
        for p in self.pages:
            if p.alert.alert_id == alert_id and p.acked_at is None:
                p.acked_at, p.acked_by = at, by
                return True
        return False

    def advance(self, now: datetime) -> None:
        """Escalate every unacknowledged page whose next escalation time has come."""
        for p in self.pages:
            steps = self.receivers[p.receiver].get("escalation", [])
            for step in steps[len(p.escalations):]:
                due = p.sent_at + timedelta(minutes=step["after_minutes"])
                if p.acked_at is not None and p.acked_at <= due:
                    break
                if due > now:
                    break
                p.escalations.append((due, step["to"]))


@dataclass
class Router:
    routing: dict
    automation_enabled: bool = True
    automated: list = field(default_factory=list)  # (at, rule, group) actions taken by automation
    suppressed: list = field(default_factory=list)  # automation the switch or the rate limit stopped

    def receivers_for(self, alert: AlertRecord) -> list[str]:
        by_rule = self.routing["routes"].get("by_rule", {})
        if alert.rule in by_rule:
            return list(by_rule[alert.rule])
        return list(self.routing["routes"]["default"][alert.category][alert.severity])

    def _automation_allowed(self, alert: AlertRecord) -> bool:
        auto = self.routing["automation"]
        if alert.rule not in auto["allowed_rules"]:
            return False
        if not self.automation_enabled:
            return False
        recent = [a for a in self.automated if a[0] > alert.at - timedelta(hours=1)]
        return len(recent) < auto["max_actions_per_hour"]

    def dispatch(self, alert: AlertRecord, pager: Pager, trip=None) -> list[str]:
        """Deliver `alert`. `trip(group, actor, reason)` trips a kill switch. Returns what was done."""
        done = []
        for receiver in self.receivers_for(alert):
            kind = self.routing["receivers"][receiver]["kind"]
            if kind == "automation":
                if self._automation_allowed(alert) and trip is not None:
                    trip(alert.group, f"detection:{alert.rule}", alert.summary)
                    self.automated.append((alert.at, alert.rule, alert.group))
                    done.append(f"automation:{receiver}")
                else:  # switched off, over the hourly limit, or no way to trip from here: a person decides
                    why = "automation-unavailable" if self._automation_allowed(alert) else "automation-suppressed"
                    self.suppressed.append((alert.at, alert.rule, alert.group))
                    fallback = self.routing["automation"]["fallback_receiver"]
                    pager.page(alert, fallback, alert.at)
                    done.append(f"page:{fallback}:{why}")
            elif kind == "page":
                pager.page(alert, receiver, alert.at)
                done.append(f"page:{receiver}")
            else:
                pager.ticket(alert, receiver, alert.at)
                done.append(f"ticket:{receiver}")
        return done

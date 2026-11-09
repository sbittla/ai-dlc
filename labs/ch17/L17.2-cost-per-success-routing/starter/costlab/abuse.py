"""A simulated abuse burst against Relay's triage spend quota (relay.routing.SpendQuota, the real code).

For an hour, stolen tokens post tickets at the API's rate limit while 40 real users post at the peak hour's
rate. Each queued ticket reserves the reasoning route's ceiling against its user and the workspace (ADR-043's
service hook). Without quotas every ticket would be triaged; with them, a user who has reserved a day's limit
gets 429 until UTC midnight. The scenarios are configured in data/abuse.json; nothing is measured.
"""

from __future__ import annotations

import random
import tempfile
from dataclasses import dataclass
from pathlib import Path

from relay.routing import PRICES, QuotaLimits, SpendQuota, call_cost

from . import DATA_DIR, load_json
from .production import CONFIGS, system_prompt

ABUSE = load_json(DATA_DIR / "abuse.json")


def ceiling_usd(mean_ticket_chars: float = 97.0) -> float:
    """The reservation per ticket: the hard route's most expensive call (input estimated at 4 characters a token)."""
    hard = CONFIGS["configs"]["routed"]["hard"]
    tokens_in = int((len(system_prompt()) + mean_ticket_chars + len("<ticket>\n\n</ticket>")) // 4)
    return call_cost(PRICES[hard["model"]], tokens_in, hard["max_output_tokens"])


@dataclass(frozen=True)
class BurstResult:
    scenario: str
    attacker_sent: int
    attacker_accepted: int
    legit_sent: int
    legit_accepted: int
    first_refusal_s: float | None   # seconds after the start of the first refusal of an attacker ticket
    reserved_usd: float             # ceiling dollars reserved against the workspace
    refusals_recorded: int


def requests(scenario: str) -> list[tuple[float, str, bool]]:
    """(seconds from the start, principal user, is_attacker) for every ticket posted in the hour, in time order."""
    cfg, legit = ABUSE["scenarios"][scenario], ABUSE["legitimate"]
    rng = random.Random(f"{ABUSE['seed']}|{scenario}")
    out = []
    for minute in range(ABUSE["minutes"]):
        for k in range(cfg["attacker_tokens"]):
            for i in range(cfg["per_token_per_minute"]):
                out.append((minute * 60 + (i + rng.random()) * 60 / cfg["per_token_per_minute"], f"user:{9001 + k}", True))
        whole = int(legit["per_minute"])
        n = whole + (1 if rng.random() < legit["per_minute"] - whole else 0)
        for _ in range(n):
            out.append((minute * 60 + rng.random() * 60, f"user:{100 + rng.randrange(legit['users'])}", False))
    return sorted(out)


def burst(scenario: str, quotas: bool = True) -> BurstResult:
    """TODO 4. Replay one scenario through SpendQuota (or with no quota: everything accepted).

    Use a SpendQuota on a fresh database file in a temporary folder, with QuotaLimits(ABUSE["limits"]). For the
    n-th request (0-based) reserve ceiling_usd() for [its user, "workspace:ws-1"] at ABUSE["start_epoch"] +
    its time, with ref f"job:ws-1:{scenario}-{n}". Count what each class sent and had accepted, note the time of
    the first refused attacker ticket, and read the workspace's reserved dollars and the number of refusals the
    ledger recorded. Without quotas, everything is accepted and reserved_usd is what the quota would have reserved.
    """
    raise NotImplementedError("TODO 4")

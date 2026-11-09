"""Checks on audit trails: chain integrity against anchors, and attribution (reference solution).

The chain itself is Relay's (`relay.audit.trail.verify`); this module adds the questions a reviewer asks
of a trail: does every action name an agent from the registry, its accountable owner and a person, and
how much of the old request log could answer the same question.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from relay.audit import AgentRegistry, Verification, load, verify

from .detect import Event


@dataclass(frozen=True)
class Attribution:
    records: int
    attributed: int
    unattributed: tuple[int, ...]  # seq numbers


def load_anchors(path: Path) -> list[tuple[int, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(a["seq"], a["hash"]) for a in data["anchors"]]


def verify_with_anchors(records: list[dict], anchors: list[tuple[int, str]]) -> Verification:
    """The chain check, then every anchor in order; the first problem found is returned."""
    result = verify(records)
    if not result.ok:
        return result
    for anchor in anchors:
        result = verify(records, anchor)
        if not result.ok:
            return result
    return result


def attribution(records: list[dict], registry: AgentRegistry) -> Attribution:
    """A record is attributed when all of these hold:

    - agent_id names an agent in the registry, and owner equals that agent's registered owner;
    - for "killswitch.*" actions: detail["actor"] is present (a person or an automation label);
    - for every other action: on_behalf_of is a person in the registry, and, if the agent's delegation is
      "required", one of its delegators.
    Records are counted in order; `unattributed` lists the seq of every record that fails.
    """
    bad = []
    for r in records:
        try:
            agent = registry.get(r.get("agent_id"))
        except KeyError:
            bad.append(r["seq"])
            continue
        if r.get("owner") != agent.owner:
            bad.append(r["seq"])
            continue
        if r["action"].startswith("killswitch."):
            if not (r.get("detail") or {}).get("actor"):
                bad.append(r["seq"])
            continue
        person = r.get("on_behalf_of")
        if person not in registry.people or (agent.delegation == "required" and person not in agent.delegators):
            bad.append(r["seq"])
    return Attribution(len(records), len(records) - len(bad), tuple(bad))


def replay_attribution(events: list[Event], raw_lines: list[dict]) -> tuple[int, int, int]:
    """(events, naming an agent, naming a person) in the pre-4.23.0 request log (provided)."""
    agent = sum(1 for r in raw_lines if r.get("agent_id"))
    person = sum(1 for r in raw_lines if r.get("on_behalf_of"))
    return len(events), agent, person


def load_trail(path: Path) -> list[dict]:
    return load(Path(path))

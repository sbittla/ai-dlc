"""Load the drivers, the architecture options and what-if scenarios (provided).

Formats are documented in data/ by example; see scripts/generate_data.py.
A score is an integer from 0 to 3 (see `SCALE`) with a reason. A driver's
weight is an integer from 0 to 5; weight 0 means "not architecture-significant",
and such drivers are listed but not scored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

SCALE = {0: "cannot meet", 1: "meets only with high risk or effort", 2: "meets", 3: "meets with margin"}
MAX_SCORE = 3


@dataclass(frozen=True)
class Driver:
    id: str
    kind: str        # nfr | constraint
    category: str
    title: str
    weight: int      # 0-5; 0 = not architecture-significant
    must: bool       # a score of 0 on a must driver disqualifies the option
    source: str
    note: str = ""


@dataclass(frozen=True)
class Score:
    value: int
    why: str


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    kind: str        # process | datastore | broker | external
    deployable: str | None


@dataclass(frozen=True)
class Flow:
    src: str
    dst: str
    sync: bool
    boundary: str | None
    data: str


@dataclass(frozen=True)
class Option:
    id: str
    name: str
    summary: str
    components: tuple[Component, ...]
    flows: tuple[Flow, ...]
    boundaries: dict[str, str]
    step_path: tuple[str, ...]
    scores: dict[str, Score]


@dataclass(frozen=True)
class Catalogue:
    version: str
    scored_by: str
    people: tuple[str, ...]
    decisions: dict[str, str]
    drivers: tuple[Driver, ...]

    def known_ids(self) -> set[str]:
        return set(self.decisions) | {d.id for d in self.drivers}


def load_catalogue(path: str | Path) -> Catalogue:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    drivers = tuple(Driver(d["id"], d["kind"], d["category"], d["title"], d["weight"], d["must"],
                           d["source"], d.get("note", "")) for d in data["drivers"])
    return Catalogue(data["version"], data["scored_by"], tuple(data["people"]), dict(data["decisions"]), drivers)


def load_option(path: str | Path) -> Option:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Option(
        id=data["id"], name=data["name"], summary=data["summary"],
        components=tuple(Component(c["id"], c["name"], c["kind"], c["deployable"]) for c in data["components"]),
        flows=tuple(Flow(f["from"], f["to"], f["sync"], f["boundary"], f["data"]) for f in data["flows"]),
        boundaries=dict(data["boundaries"]),
        step_path=tuple(data["step_path"]),
        scores={k: Score(v[0], v[1]) for k, v in data["scores"].items()},
    )


def load_options(paths) -> list[Option]:
    return [load_option(p) for p in paths]


def apply_scenario(catalogue: Catalogue, options: list[Option], path: str | Path) -> tuple[Catalogue, list[Option], dict]:
    """Return copies with the scenario's weights and scores substituted, and the scenario itself."""
    sc = json.loads(Path(path).read_text(encoding="utf-8"))
    drivers = tuple(replace(d, weight=sc.get("weights", {}).get(d.id, d.weight)) for d in catalogue.drivers)
    out = []
    for opt in options:
        changes = sc.get("scores", {}).get(opt.id, {})
        scores = {k: (Score(changes[k], f"scenario {sc['name']}") if k in changes else v)
                  for k, v in opt.scores.items()}
        out.append(replace(opt, scores=scores))
    return replace(catalogue, drivers=drivers), out, sc

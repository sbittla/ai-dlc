"""Read OpenTofu's JSON plan format (`tofu show -json <planfile>`). Provided; no TODOs here.

The parts this lab uses, from the format OpenTofu shares with Terraform (format_version 1.x):

    resource_changes[]              one entry per resource instance
      .address  .type  .name  .index
      .change.actions               ["create"], ["update"], ["delete"], ["delete", "create"], ["no-op"] ...
      .change.before / .after       attribute values; values unknown until apply are left out of
                                    objects, and replaced by null inside lists
      .change.after_unknown         the same shape, with true wherever a value is unknown
    configuration.root_module.resources[].expressions
                                    what the configuration set: {"constant_value": v} or
                                    {"references": ["aws_x.y.id", "aws_x.y"]}, nested blocks as lists
    variables.<name>.value          the input variables

A value can be absent from `after` for two reasons: it is not set, or it is not known yet. Only
`after_unknown` tells them apart, and only `configuration` tells "computed by the provider" from
"set to something that depends on another resource". A check that confuses them either misses a
problem or raises a false alarm, so the helpers below keep the three apart.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Resource:
    address: str
    type: str
    name: str
    index: object
    actions: tuple[str, ...]
    after: dict
    unknown: dict
    before: dict | None
    config: dict = field(default_factory=dict)

    @property
    def config_address(self) -> str:
        """The address in `configuration`, which has no instance index (`aws_instance.model`)."""
        return f"{self.type}.{self.name}"


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_overlay(plan: dict, overlay: dict) -> dict:
    """A seeded case: the clean plan with some resources removed and some added or replaced."""
    out = copy.deepcopy(plan)
    gone = set(overlay.get("remove", []))
    sections = [(out["resource_changes"], "resource_change"),
                (out["planned_values"]["root_module"].setdefault("resources", []), "planned_value"),
                (out["configuration"]["root_module"].setdefault("resources", []), "configuration")]
    for items, _ in sections:
        items[:] = [r for r in items if r["address"] not in gone]
    for entry in overlay.get("upsert", []):
        for items, key in sections:
            new = entry.get(key)
            if new is None:
                continue
            for i, r in enumerate(items):
                if r["address"] == new["address"]:
                    items[i] = new
                    break
            else:
                items.append(new)
    return out


def load_plan(path: str | Path, overlay: str | Path | None = None) -> dict:
    plan = load_json(path)
    return apply_overlay(plan, load_json(overlay)) if overlay else plan


def resources(plan: dict, actions: tuple[str, ...] = ("create", "update")) -> list[Resource]:
    """Every resource instance whose change includes one of `actions`, joined with its configuration."""
    config = {r["address"]: r.get("expressions", {})
              for r in plan.get("configuration", {}).get("root_module", {}).get("resources", [])}
    out = []
    for rc in plan.get("resource_changes", []):
        ch = rc["change"]
        if rc.get("mode", "managed") != "managed" or not set(ch["actions"]) & set(actions):
            continue
        out.append(Resource(rc["address"], rc["type"], rc["name"], rc.get("index"), tuple(ch["actions"]),
                            ch.get("after") or {}, ch.get("after_unknown") or {}, ch.get("before"),
                            config.get(f"{rc['type']}.{rc['name']}", {})))
    return out


def of_type(rs: list[Resource], *types: str) -> list[Resource]:
    return [r for r in rs if r.type in types]


def _walk(value, path):
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and isinstance(key, int) and 0 <= key < len(value):
            value = value[key]
        else:
            return None
    return value


def is_unknown(r: Resource, *path) -> bool:
    """True if the value at `path` (or any part of it) is unknown until apply."""
    marker = _walk(r.unknown, path)
    if marker is True:
        return True
    if isinstance(marker, (dict, list)):
        return _contains_true(marker)
    # An unknown parent makes everything below it unknown.
    return any(_walk(r.unknown, path[:i]) is True for i in range(1, len(path)))


def _contains_true(marker) -> bool:
    if marker is True:
        return True
    if isinstance(marker, dict):
        return any(_contains_true(v) for v in marker.values())
    if isinstance(marker, list):
        return any(_contains_true(v) for v in marker)
    return False


def get(r: Resource, *path, default=None):
    """The known value at `path` in `after`, or `default` if it is absent (unset or unknown)."""
    value = _walk(r.after, path)
    return default if value is None else value


def configured(r: Resource, attr: str) -> bool:
    """True if the configuration sets `attr`; False if it is left to the provider."""
    return attr in r.config


def reference(r: Resource, attr: str) -> str | None:
    """The address of the resource that a top-level attribute refers to, for example
    `aws_security_group.egress_proxy` for a rule's `security_group_id`. None if not a reference."""
    refs = r.config.get(attr, {}).get("references", []) if isinstance(r.config.get(attr), dict) else []
    for ref in refs:
        parts = ref.split(".")
        if len(parts) == 2 and parts[0].startswith("aws_"):
            return ref
    return None


def referring(rs: list[Resource], type_: str, attr: str, target: str) -> list[Resource]:
    """Resources of `type_` whose `attr` refers to `target` (for example the public access block of a bucket)."""
    return [r for r in rs if r.type == type_ and reference(r, attr) == target]


def policy_document(r: Resource, attr: str = "policy") -> dict | None:
    """A JSON policy attribute, parsed. None if it is unknown or absent."""
    raw = get(r, attr)
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


def statements(doc: dict) -> list[dict]:
    """The policy's statements, each with Action, NotAction and Resource as lists."""
    raw = doc.get("Statement", [])
    out = []
    for s in raw if isinstance(raw, list) else [raw]:
        s = dict(s)
        for key in ("Action", "NotAction", "Resource", "NotResource"):
            if key in s and not isinstance(s[key], list):
                s[key] = [s[key]]
        out.append(s)
    return out


def variable(plan: dict, name: str, default=None):
    return plan.get("variables", {}).get(name, {}).get("value", default)


def region(plan: dict) -> str | None:
    """The provider's region: a variable, or a constant in the provider configuration."""
    expr = plan.get("configuration", {}).get("provider_config", {}).get("aws", {}).get("expressions", {})
    region_expr = expr.get("region", {})
    if "constant_value" in region_expr:
        return region_expr["constant_value"]
    return variable(plan, "region")

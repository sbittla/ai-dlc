"""The engine's contract boundary: documents in and out, checked against JSON Schema.

`to_document` turns the engine's dataclasses into the JSON documents the
contract describes, and `rule_from_document` reads a Rule document back.
`validate` checks a document against a schema. It is a
small standard-library validator for the subset of JSON Schema (2020-12) the
contract uses, and it fails closed in three ways:

- `check_schema` walks the whole schema before any document is checked, and
  refuses any keyword it does not implement, wherever it appears;
- it refuses keywords beside a `$ref`, which it would otherwise ignore;
- `enum` and `const` compare types as well as values, so `true` never equals `1`.

So the contract cannot quietly rely on a rule nobody checks.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta

from .model import BusinessHours, Rule, Step

SUPPORTED = {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
             "minimum", "maximum", "minItems", "maxItems", "uniqueItems", "pattern", "$ref", "$defs"}
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "examples"}
JSON_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def to_document(value):
    """A JSON-ready copy of a dataclass, tuple, frozenset or datetime (UTC, whole seconds, 'Z').

    An optional field (one whose default is None) is left out while it is None,
    so a 1.0.0 rule's document is exactly what 1.0.0 produced. Required fields
    that may be null, such as `Evaluation.next_due_at`, are always present.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_document(getattr(value, f.name)) for f in dataclasses.fields(value)
                if not (f.default is None and getattr(value, f.name) is None)}
    if isinstance(value, datetime):
        if value.utcoffset() != timedelta(0):
            raise ValueError("datetimes in documents must be UTC")
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, frozenset):
        return sorted(to_document(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [to_document(v) for v in value]
    return value


def rule_from_document(document: dict) -> Rule:
    """A Rule from a Rule document that has already passed `validate` against the contract.

    Optional fields left out of the document are None. Nothing is repaired or
    guessed: the caller validates first, and validate_rule decides the rest.
    """
    hours = document.get("business_hours")
    return Rule(document["rule_id"], document["project_id"], document["priority"],
                tuple(Step(s["number"], s["delay_minutes"], tuple(s["targets"])) for s in document["steps"]),
                document.get("name"),
                None if hours is None else BusinessHours(hours["start"], hours["end"], hours["time_zone"],
                                                         tuple(hours["days"])))


def to_rule_document(rule: Rule) -> dict:
    """A Rule's contract document (to_document, named for readers of the routes)."""
    return to_document(rule)


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return type(value) is int
    if name == "number":
        return type(value) in (int, float)
    return isinstance(value, JSON_TYPES[name]) and not (name != "boolean" and type(value) is bool)


def _same(a, b) -> bool:
    """JSON equality: booleans equal only booleans; 1 and 1.0 are equal numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    return a == b


def check_schema(schema: dict, path: str = "#") -> None:
    """Raise ValueError if any part of `schema` uses something `validate` does not implement."""
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: a schema must be an object")
    keys = {k for k in schema if k not in ANNOTATIONS and not k.startswith("x-")}
    unknown = keys - SUPPORTED
    if unknown:
        raise ValueError(f"{path}: schema keyword(s) not implemented: {sorted(unknown)}")
    if "$ref" in schema:
        if keys - {"$ref"}:
            raise ValueError(f"{path}: keywords beside $ref are not supported: {sorted(keys - {'$ref'})}")
        if not str(schema["$ref"]).startswith("#/$defs/"):
            raise ValueError(f"{path}: only local '#/$defs/...' references are supported, got {schema['$ref']!r}")
    if not isinstance(schema.get("additionalProperties", True), bool):
        raise ValueError(f"{path}: only true or false is supported for additionalProperties")
    for name, sub in schema.get("properties", {}).items():
        check_schema(sub, f"{path}/properties/{name}")
    for name, sub in schema.get("$defs", {}).items():
        check_schema(sub, f"{path}/$defs/{name}")
    if "items" in schema:
        check_schema(schema["items"], f"{path}/items")


def validate(instance, schema: dict, root: dict | None = None) -> list[str]:
    """Every way `instance` breaks `schema`, as 'path: problem' strings; [] if it conforms.

    `root` holds the `$defs` that references point to; it defaults to `schema`.
    Both are checked with check_schema first, so an unsupported keyword anywhere
    raises ValueError even if this document never reaches it.
    """
    root = schema if root is None else root
    check_schema(root)
    if schema is not root:
        check_schema(schema)
    defs = root.get("$defs", {})
    for ref in sorted(_refs(root) | _refs(schema)):
        if ref.split("/")[-1] not in defs:
            raise ValueError(f"$ref {ref!r} points to no definition in the schema's $defs")
    return _validate(instance, schema, root, "$")


def _refs(node) -> set[str]:
    """Every $ref anywhere in a schema."""
    if isinstance(node, dict):
        found = {node["$ref"]} if isinstance(node.get("$ref"), str) else set()
        return found.union(*(_refs(v) for v in node.values())) if node else found
    if isinstance(node, list):
        return set().union(*(_refs(v) for v in node)) if node else set()
    return set()


def _validate(instance, schema: dict, root: dict, path: str) -> list[str]:
    if "$ref" in schema:
        return _validate(instance, root["$defs"][schema["$ref"].split("/")[-1]], root, path)
    errors = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, t) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {type(instance).__name__}"]
    if "const" in schema and not _same(instance, schema["const"]):
        errors.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and not any(_same(instance, v) for v in schema["enum"]):
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if isinstance(instance, (int, float)) and type(instance) is not bool:
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is less than {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} is greater than {schema['maximum']}")
    if isinstance(instance, str) and "pattern" in schema and not re.search(schema["pattern"], instance):
        errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} item(s)")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} item(s)")
        if schema.get("uniqueItems") and any(_same(a, b) for i, a in enumerate(instance) for b in instance[i + 1:]):
            errors.append(f"{path}: items are not unique")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += _validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required field {name!r}")
        for name, value in instance.items():
            if name in props:
                errors += _validate(value, props[name], root, f"{path}.{name}")
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"{path}: field {name!r} is not in the contract")
    return errors

"""The slice's contract boundary: documents in and out, checked against JSON Schema.

`to_document` turns the slice's dataclasses into the JSON documents the
contract describes. `validate` checks a document against a schema. It is a
small standard-library validator for the subset of JSON Schema (2020-12) the
contract uses. It fails closed: a schema keyword it does not implement raises
an error instead of being ignored, so the contract cannot quietly rely on a
rule nobody checks.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta

SUPPORTED = {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
             "minimum", "maximum", "minItems", "maxItems", "uniqueItems", "pattern", "$ref", "$defs"}
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "examples"}
JSON_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def to_document(value):
    """A JSON-ready copy of a dataclass, tuple, frozenset or datetime (UTC, whole seconds, 'Z')."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_document(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, datetime):
        if value.utcoffset() != timedelta(0):
            raise ValueError("datetimes in documents must be UTC")
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, frozenset):
        return sorted(to_document(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [to_document(v) for v in value]
    return value


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return type(value) is int
    if name == "number":
        return type(value) in (int, float)
    return isinstance(value, JSON_TYPES[name]) and not (name != "boolean" and type(value) is bool)


def validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Every way `instance` breaks `schema`, as 'path: problem' strings; [] if it conforms."""
    root = schema if root is None else root
    unknown = {k for k in schema if k not in SUPPORTED | ANNOTATIONS and not k.startswith("x-")}
    if unknown:
        raise ValueError(f"{path}: schema keyword(s) not implemented: {sorted(unknown)}")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"{path}: only local '#/$defs/...' references are supported, got {ref!r}")
        return validate(instance, root["$defs"][ref.split("/")[-1]], root, path)
    if not isinstance(schema.get("additionalProperties", True), bool):
        raise ValueError(f"{path}: only true or false is supported for additionalProperties")
    errors = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, t) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
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
        if schema.get("uniqueItems") and len({repr(v) for v in instance}) != len(instance):
            errors.append(f"{path}: items are not unique")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required field {name!r}")
        for name, value in instance.items():
            if name in props:
                errors += validate(value, props[name], root, f"{path}.{name}")
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"{path}: field {name!r} is not in the contract")
    return errors

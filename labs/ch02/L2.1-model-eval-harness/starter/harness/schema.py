"""A deliberately small JSON Schema validator, and Relay's triage schema.

Production code should use a full validator (for example the `jsonschema`
package) or the model provider's structured-output feature. This lab
implements the subset it needs so you can see exactly what "schema-valid"
means: right types, required fields present, values from the allowed set,
and nothing extra.
"""

from __future__ import annotations

TRIAGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["bug", "feature_request", "billing", "access", "how_to"]},
        "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
        "team": {"type": "string", "enum": ["platform", "payments", "identity", "docs"]},
    },
    "required": ["category", "priority", "team"],
    "additionalProperties": False,
}

_TYPES = {
    "object": dict,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
}


def validate(value, schema: dict, path: str = "$") -> list[str]:
    """Return a list of human-readable errors; an empty list means valid.

    Supports: type, enum, properties, required, additionalProperties (False
    only) and items. Booleans are not accepted where integers are expected.
    """
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        py_type = _TYPES[expected]
        if isinstance(value, bool) and expected in ("integer", "number"):
            return [f"{path}: expected {expected}, got boolean"]
        if not isinstance(value, py_type):
            return [f"{path}: expected {expected}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if expected == "object":
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required field {name!r}")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in props:
                    errors.append(f"{path}: unexpected field {name!r}")
        for name, sub in props.items():
            if name in value:
                errors.extend(validate(value[name], sub, f"{path}.{name}"))
    if expected == "array" and "items" in schema:
        for i, item in enumerate(value):
            errors.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return errors

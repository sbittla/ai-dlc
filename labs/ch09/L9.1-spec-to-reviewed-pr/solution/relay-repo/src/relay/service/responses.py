"""Small HTTP helpers shared by the service's route modules: responses, errors and JSON bodies.

Errors never echo request bodies, so ticket text and rule documents cannot
leak into logs or error pages through this layer.
"""

from __future__ import annotations

import json

MAX_BODY_BYTES = 16_384
MAX_JSON_DEPTH = 4


class Response:
    def __init__(self, status: int, body: dict, headers: dict[str, str] | None = None) -> None:
        self.status, self.body, self.headers = status, body, dict(headers or {})


def error(status: int, message: str, **headers: str) -> Response:
    return Response(status, {"error": message}, headers)


def read_json(environ: dict, max_depth: int = MAX_JSON_DEPTH) -> tuple[object, Response | None]:
    """The request body as JSON, or an error response: 411, 413, or 400 for bad or too deeply nested JSON."""
    raw_len = environ.get("CONTENT_LENGTH") or ""
    if not raw_len.isdigit():
        return None, error(411, "Content-Length required")
    length = int(raw_len)
    if length > MAX_BODY_BYTES:
        return None, error(413, f"body over {MAX_BODY_BYTES} bytes")
    raw = environ["wsgi.input"].read(length)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None, error(400, "body is not valid JSON")
    if _depth(value, max_depth) > max_depth:
        return None, error(400, f"JSON nested deeper than {max_depth} levels")
    return value, None


def _depth(value, limit: int, level: int = 1) -> int:
    if level > limit:
        return level
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return max((_depth(c, limit, level + 1) for c in children), default=level)

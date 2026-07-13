"""Small, deterministic JSON serialization helpers."""

import json
from typing import cast

from pydantic import JsonValue


def dumps_json(value: JsonValue, *, pretty: bool = False) -> str:
    """Serialize a JSON-compatible value with deterministic key ordering."""

    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def loads_json(value: str) -> JsonValue:
    """Parse JSON and expose its recursive value type to callers."""

    return cast(JsonValue, json.loads(value))

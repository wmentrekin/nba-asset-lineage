from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_part(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value)


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    joined = "|".join(_stable_part(value) for value in parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def stable_payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

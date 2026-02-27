from __future__ import annotations

import hashlib
import re
from typing import Iterable


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "na"


def deterministic_id(prefix: str, parts: Iterable[str], hash_len: int = 10) -> str:
    material = "|".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:hash_len]
    slug_part = _slug(material)[:48]
    return f"{prefix}_{slug_part}_{digest}"


def deterministic_event_id(team_code: str, event_key: str, event_date: str, event_type: str) -> str:
    return deterministic_id("evt", [team_code, event_key, event_date, event_type])


def deterministic_asset_id(team_code: str, asset_key: str) -> str:
    return deterministic_id("ast", [team_code, asset_key])


def deterministic_edge_id(asset_id: str, source_node_id: str, target_node_id: str, segment_index: int) -> str:
    return deterministic_id("edg", [asset_id, source_node_id, target_node_id, str(segment_index)])

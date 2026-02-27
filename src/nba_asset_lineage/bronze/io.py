from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no} must be a JSON object")
        yield payload


def _iter_json(path: Path) -> Iterable[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"{path}[{index}] must be a JSON object")
            yield item
        return
    if isinstance(payload, dict):
        yield payload
        return
    raise ValueError(f"Unsupported JSON payload in {path}")


def load_raw_records(base_dir: Path, entity: str) -> list[dict[str, Any]]:
    entity_dir = base_dir / entity
    if not entity_dir.exists():
        return []

    files = sorted(entity_dir.rglob("*.jsonl")) + sorted(entity_dir.rglob("*.json"))
    records: list[dict[str, Any]] = []
    for path in files:
        if path.suffix == ".jsonl":
            records.extend(_iter_jsonl(path))
        elif path.suffix == ".json":
            records.extend(_iter_json(path))
    return records

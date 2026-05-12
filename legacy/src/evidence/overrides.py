from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from evidence.models import OverrideBundle, OverrideLink, OverrideRecord
from evidence.override_schema import validate_override_bundle_payload
from shared.ids import stable_id


def _iter_override_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    patterns = ("*.yaml", "*.yml", "*.json")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(root.rglob(pattern)))
    return files


def _load_structured_file(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw_text)
    else:
        data = yaml.safe_load(raw_text)
    if data is None:
        return {}
    if isinstance(data, list):
        return {"overrides": data}
    if not isinstance(data, dict):
        raise ValueError(f"Override file must contain a mapping or list at top level: {path}")
    return data


def load_override_bundle(root: Path | str, *, default_authored_by: str = "local") -> OverrideBundle:
    root_path = Path(root)
    overrides: list[OverrideRecord] = []
    override_links: list[OverrideLink] = []

    for path in _iter_override_files(root_path):
        payload = _load_structured_file(path)
        validated_bundle = validate_override_bundle_payload(payload, source=str(path))
        created_at = datetime.utcnow()
        for entry in validated_bundle.overrides:
            override_id = entry.override_id or stable_id(
                "override",
                path.relative_to(root_path),
                entry.override_type,
                entry.target_type,
                entry.target_key,
                entry.payload,
            )
            override_record = OverrideRecord(
                override_id=override_id,
                override_type=entry.override_type,
                target_type=entry.target_type,
                target_key=entry.target_key,
                payload=dict(entry.payload),
                reason=entry.reason,
                authored_by=entry.authored_by or default_authored_by,
                authored_at=entry.authored_at or created_at,
                is_active=entry.is_active,
            )
            overrides.append(override_record)

            for link_entry in entry.links:
                override_links.append(
                    OverrideLink(
                        override_link_id=link_entry.override_link_id
                        or stable_id(
                            "override_link",
                            override_record.override_id,
                            link_entry.source_record_id,
                            link_entry.claim_id,
                        ),
                        override_id=override_record.override_id,
                        source_record_id=link_entry.source_record_id,
                        claim_id=link_entry.claim_id,
                    )
                )

    return OverrideBundle(overrides=overrides, override_links=override_links)


def load_overrides(root: Path | str, *, default_authored_by: str = "local") -> list[OverrideRecord]:
    return load_override_bundle(root, default_authored_by=default_authored_by).overrides


ingest_overrides = load_overrides


def insert_override_bundle(conn: Any, bundle: OverrideBundle) -> dict[str, int]:
    inserted_overrides = 0
    inserted_links = 0
    with conn.cursor() as cur:
        for override in bundle.overrides:
            cur.execute(
                """
                insert into evidence.overrides (
                    override_id,
                    override_type,
                    target_type,
                    target_key,
                    payload,
                    reason,
                    authored_by,
                    authored_at,
                    is_active
                )
                values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                on conflict (override_id) do update
                set override_type = excluded.override_type,
                    target_type = excluded.target_type,
                    target_key = excluded.target_key,
                    payload = excluded.payload,
                    reason = excluded.reason,
                    authored_by = excluded.authored_by,
                    authored_at = excluded.authored_at,
                    is_active = excluded.is_active
                """,
                (
                    override.override_id,
                    override.override_type,
                    override.target_type,
                    override.target_key,
                    json.dumps(override.payload, sort_keys=True, default=str),
                    override.reason,
                    override.authored_by,
                    override.authored_at,
                    override.is_active,
                ),
            )
            inserted_overrides += 1

        for link in bundle.override_links:
            cur.execute(
                """
                insert into evidence.override_links (
                    override_link_id,
                    override_id,
                    source_record_id,
                    claim_id
                )
                values (%s, %s, %s, %s)
                on conflict (override_link_id) do update
                set override_id = excluded.override_id,
                    source_record_id = excluded.source_record_id,
                    claim_id = excluded.claim_id
                """,
                (
                    link.override_link_id,
                    link.override_id,
                    link.source_record_id,
                    link.claim_id,
                ),
            )
            inserted_links += 1

    return {
        "override_count": inserted_overrides,
        "override_link_count": inserted_links,
    }

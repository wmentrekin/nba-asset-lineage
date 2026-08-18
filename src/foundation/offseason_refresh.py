"""Small, explicit adapter for the reviewed 2026 Memphis offseason update.

This deliberately uses the existing locked-source loaders and the existing derived
and canonical rebuilds.  It is not part of the sealed-refresh experiment: its
only special behaviour is promoting the exact official-release rows that were
reviewed in the checked-in reconciliation file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import psycopg

from foundation.canonical import load_foundation_canonical_bundle
from foundation.ingest import load_derived_foundation_entities
from foundation.live_sources import (
    load_bref_draft_results,
    load_nba_player_movement,
    load_official_release_sources,
    preflight_locked_source_bundle,
)
from foundation.source_payloads import load_source_bundle


NBA_PLAYER_MOVEMENT_SCOPE = {
    "endpoint_url": "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"
}
DEFAULT_RECONCILIATION_PATH = Path("configs/data/memphis_official_canonical_reconciliation_2026.json")


def load_official_promotion_manifest(path: Path = DEFAULT_RECONCILIATION_PATH) -> list[dict[str, object]]:
    """Return the closed set of official source-event promotions.

    Keeping this validation outside the database operation makes the data decision
    reviewable and prevents a malformed reconciliation file from silently changing
    which corroboration-only rows become canonical inputs.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("manifest_version") != "official_canonical_reconciliation_v1":
        raise ValueError("Official canonical reconciliation manifest has an unsupported schema.")
    if payload.get("team_scope") != "MEM":
        raise ValueError("Official canonical reconciliation manifest must be Memphis scoped.")
    groups = payload.get("reconciliation_groups")
    if not isinstance(groups, list):
        raise ValueError("Official canonical reconciliation manifest must contain reconciliation_groups.")

    promotions: list[dict[str, object]] = []
    source_event_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or group.get("disposition") != "promote":
            continue
        ids = group.get("canonical_member_source_event_ids")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not ids[0]:
            raise ValueError("Each promoted official reconciliation group must name exactly one source event.")
        source_event_id = ids[0]
        if source_event_id in source_event_ids:
            raise ValueError(f"Duplicate promoted official source event: {source_event_id}")
        source_event_ids.add(source_event_id)
        event_date = group.get("event_date")
        event_type = group.get("event_type")
        if not isinstance(event_date, str) or not isinstance(event_type, str):
            raise ValueError(f"Promoted official event {source_event_id} is missing date or type.")
        promotions.append(
            {
                "source_event_id": source_event_id,
                "event_date": event_date,
                "event_type": event_type,
                "source_group_hint": group.get("source_group_hint"),
                "reconciliation_key": group.get("reconciliation_key"),
                "precedence": group.get("precedence"),
            }
        )
    if len(promotions) != 7:
        raise ValueError(f"Expected exactly seven promoted official events, found {len(promotions)}.")
    return promotions


def promote_official_events(
    database_url: str,
    *,
    reconciliation_path: Path = DEFAULT_RECONCILIATION_PATH,
) -> dict[str, object]:
    """Promote exactly the reconciled official rows, idempotently, in one transaction."""
    promotions = load_official_promotion_manifest(reconciliation_path)
    ids = [str(item["source_event_id"]) for item in promotions]
    by_id = {str(item["source_event_id"]): item for item in promotions}
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select source_event_id, event_date::text, event_type
                from foundation.source_event
                where source_event_id = any(%s)
                """,
                (ids,),
            )
            found = {str(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}
            missing = sorted(set(ids).difference(found))
            if missing:
                raise ValueError(f"Cannot promote official events not loaded from the locked bundle: {missing}")
            for source_event_id, promotion in by_id.items():
                if found[source_event_id] != (promotion["event_date"], promotion["event_type"]):
                    raise ValueError(f"Official reconciliation does not match loaded event {source_event_id}.")
                cursor.execute(
                    """
                    update foundation.source_event
                    set source_group_hint = %s,
                        normalized_payload = (normalized_payload - 'canonical_exclusion_reason' - 'corroboration_only')
                          || jsonb_build_object(
                              'canonical_promotion', jsonb_build_object(
                                  'reconciliation_key', %s::text,
                                  'precedence', %s::text
                              )
                          )
                    where source_event_id = %s
                    """,
                    (
                        promotion["source_group_hint"],
                        promotion["reconciliation_key"],
                        promotion["precedence"],
                        source_event_id,
                    ),
                )
        connection.commit()
    return {"promoted_source_events": len(promotions), "source_event_ids": ids}


def run_locked_offseason_refresh(
    database_url: str | None,
    *,
    artifact_directory: Path,
    reconciliation_path: Path = DEFAULT_RECONCILIATION_PATH,
    execute: bool = False,
) -> dict[str, object]:
    """Preflight or apply the narrow incremental refresh from one locked artifact leaf."""
    bundle_paths = {
        "nba_player_movement": artifact_directory / "bundles" / "nba_player_movement",
        "bref_draft": artifact_directory / "bundles" / "bref_draft",
        "official_releases": artifact_directory / "bundles" / "official_releases",
    }
    expected = {
        "nba_player_movement": ("nba_player_movement", NBA_PLAYER_MOVEMENT_SCOPE),
        "bref_draft": ("bref_draft", {"team_code": "MEM"}),
        "official_releases": ("official_releases", {"team_code": "MEM"}),
    }
    bundle_digests: dict[str, str] = {}
    previews: dict[str, dict[str, object]] = {}
    for name, path in bundle_paths.items():
        bundle = load_source_bundle(path)
        source_kind, source_scope = expected[name]
        previews[name] = preflight_locked_source_bundle(
            payload_bundle_path=path,
            expected_bundle_sha256=bundle.digest,
            expected_source_kind=source_kind,
            expected_source_scope=source_scope,
        )
        bundle_digests[name] = bundle.digest
    promotions = load_official_promotion_manifest(reconciliation_path)
    result: dict[str, object] = {
        "status": "ok",
        "writes_to_database": execute,
        "artifact_directory": str(artifact_directory),
        "bundle_digests": bundle_digests,
        "preflight": previews,
        "official_promotions": [item["source_event_id"] for item in promotions],
    }
    if not execute:
        return result
    if not database_url:
        raise ValueError("database_url is required with execute=True")

    result["nba_player_movement"] = load_nba_player_movement(
        database_url, payload_bundle_path=bundle_paths["nba_player_movement"], expected_bundle_sha256=bundle_digests["nba_player_movement"], dry_run=False, execute=True
    )
    result["bref_draft"] = load_bref_draft_results(
        database_url, team_code="MEM", payload_bundle_path=bundle_paths["bref_draft"], expected_bundle_sha256=bundle_digests["bref_draft"], dry_run=False, execute=True
    )
    result["official_releases"] = load_official_release_sources(
        database_url, payload_bundle_path=bundle_paths["official_releases"], expected_bundle_sha256=bundle_digests["official_releases"], dry_run=False, execute=True
    )
    result["official_promotion"] = promote_official_events(database_url, reconciliation_path=reconciliation_path)
    result["derived_entities"] = load_derived_foundation_entities(database_url)
    result["canonical"] = load_foundation_canonical_bundle(database_url)
    return result

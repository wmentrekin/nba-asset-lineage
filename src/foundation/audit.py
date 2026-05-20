from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path
import unicodedata

import psycopg

from foundation.export import draft_resolution_event_date
from foundation.ingest import normalize_player_alias_name
from foundation.pick_inventory import DEFAULT_FUTURE_PICK_OBLIGATION_PATH
from foundation.pick_inventory import load_pick_inventory_fixture
from foundation.sources import (
    CORROBORATION_DERIVATION_PATH,
    CORROBORATION_REPORT_EVENT_FIELDS,
    CORROBORATION_REPORT_OUTPUT_KEY,
    CORROBORATION_REPORTING_UNIT,
    SOURCE_POLICY,
    SOURCE_POLICY_VERSION,
)


CURRENTNESS_VERIFIED_THROUGH = "2026-05-14"
CURRENTNESS_LAST_VERIFIED_EVENT_DATE = "2026-04-10"
CURRENTNESS_SOURCE_BASIS = (
    "Basketball-Reference Memphis transactions page",
    "NBA.com transaction and team release search",
    "CBS Sports Memphis transactions feed",
    "Memphis Grizzlies and G League official release search",
)
CORROBORATING_SOURCE_SYSTEMS = (
    "nba_player_movement",
    "nba_official",
    "team_official",
)


FOUNDATION_TABLES = (
    "source_record",
    "source_event",
    "player",
    "player_alias",
    "pick",
    "asset",
    "pick_inventory_obligation",
    "roster_baseline_player",
    "roster_snapshot",
    "roster_snapshot_player",
    "roster_snapshot_pick",
    "draft_selection",
    "draft_pick_resolution",
    "draft_lottery_result",
    "canonical_event",
    "canonical_event_member",
    "event_asset_transition",
)

AUDIT_PLAYER_SUFFIX_TOKENS = frozenset({"jr", "sr", "ii", "iii", "iv", "v", "vi", "vii"})
AUDIT_NEAR_DATE_RECONCILIATION_WINDOW_DAYS = 3
AUDIT_MAX_TRADE_MATCH_COMBINATION_SIZE = 4
# Keep this table intentionally small; expand only with source-backed cases.
AUDIT_SAFE_FIRST_NAME_VARIANTS = {
    "kenneth": frozenset({"kenny"}),
    "kenny": frozenset({"kenneth"}),
    "vince": frozenset({"vincent"}),
    "vincent": frozenset({"vince"}),
}


def audit_foundation_data(
    database_url: str,
    *,
    pick_obligation_fixture_path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
) -> dict[str, object]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        counts = count_foundation_tables(connection)
        event_span = fetch_event_span(connection)
        graph_export_span = fetch_graph_export_span(connection)
        source_coverage = fetch_source_coverage(connection)
        source_corroboration_report = build_source_corroboration_report(
            fetch_source_corroboration_events(connection)
        )
        pick_inventory = fetch_pick_inventory_metrics(connection)
        report: dict[str, object] = {
            "status": "ok",
            "counts": counts,
            "event_span": event_span,
            "event_span_currentness": build_event_span_currentness(event_span),
            "graph_export_span": graph_export_span,
            "source_coverage": source_coverage,
            "source_coverage_report": build_source_coverage_report(source_coverage),
            CORROBORATION_REPORT_OUTPUT_KEY: source_corroboration_report,
            "aliases": fetch_alias_metrics(connection),
            "snapshots": fetch_snapshot_metrics(connection),
            "pick_inventory": pick_inventory,
            "pick_inventory_fixture_gap_report": build_pick_inventory_fixture_gap_report(
                pick_obligation_fixture_path
            ),
            "draft": fetch_draft_metrics(connection),
            "canonical": {
                "events": counts.get("canonical_event", 0),
                "event_members": counts.get("canonical_event_member", 0),
                "transitions": counts.get("event_asset_transition", 0),
            },
        }
    report["draft_lineage_limitations"] = build_draft_lineage_limitations(report)
    report["known_gaps"] = build_known_gaps(report)
    return report


def count_foundation_tables(connection: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table_name in FOUNDATION_TABLES:
            cursor.execute("select to_regclass(%s)", (f"foundation.{table_name}",))
            if cursor.fetchone()[0] is None:
                counts[table_name] = 0
                continue
            cursor.execute(f"select count(*) from foundation.{table_name}")
            counts[table_name] = int(cursor.fetchone()[0])
    return counts


def fetch_event_span(connection: psycopg.Connection) -> dict[str, object]:
    if table_exists(connection, "canonical_event"):
        table_name = "canonical_event"
        date_column = "event_date"
    elif table_exists(connection, "source_event"):
        table_name = "source_event"
        date_column = "event_date"
    else:
        return {"source": None, "start_date": None, "end_date": None, "event_count": 0}

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            select min({date_column})::text, max({date_column})::text, count(*)
            from foundation.{table_name}
            """
        )
        row = cursor.fetchone()
    return {
        "source": f"foundation.{table_name}",
        "start_date": str(row[0]) if row[0] is not None else None,
        "end_date": str(row[1]) if row[1] is not None else None,
        "event_count": int(row[2]),
    }


def fetch_graph_export_span(connection: psycopg.Connection) -> dict[str, object]:
    event_span = fetch_event_span(connection)
    dates = [
        str(event_span["start_date"]),
        str(event_span["end_date"]),
    ] if event_span.get("start_date") and event_span.get("end_date") else []
    event_count = int(event_span.get("event_count", 0))
    draft_resolution_count = 0

    if table_exists(connection, "draft_pick_resolution"):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select draft_year, round_number
                from foundation.draft_pick_resolution
                """
            )
            for draft_year, round_number in cursor.fetchall():
                dates.append(draft_resolution_event_date(int(draft_year), int(round_number)))
                draft_resolution_count += 1

    return {
        "source": "foundation graph export inputs",
        "start_date": min(dates) if dates else None,
        "end_date": max(dates) if dates else None,
        "event_count": event_count + draft_resolution_count,
        "canonical_event_count": event_count,
        "draft_resolution_event_count": draft_resolution_count,
    }


def fetch_source_coverage(connection: psycopg.Connection) -> list[dict[str, object]]:
    if not table_exists(connection, "source_record"):
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select source_system, source_type, count(*) as records
            from foundation.source_record
            group by source_system, source_type
            order by source_system, source_type
            """
        )
        rows = cursor.fetchall()
    return [
        {
            "source_system": str(row[0]),
            "source_type": str(row[1]),
            "records": int(row[2]),
        }
        for row in rows
    ]


def fetch_source_corroboration_events(connection: psycopg.Connection) -> list[dict[str, object]]:
    required_tables = ("canonical_event", "canonical_event_member", "source_event", "source_record")
    if not all(table_exists(connection, table_name) for table_name in required_tables):
        return []

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select ce.canonical_event_id,
                   ce.event_date::text,
                   ce.event_type,
                   ce.sequence_on_date,
                   se.source_event_id,
                   sr.source_system,
                   sr.source_type,
                   se.normalized_payload
            from foundation.canonical_event ce
            left join foundation.canonical_event_member cem
              on cem.canonical_event_id = ce.canonical_event_id
            left join foundation.source_event se
              on se.source_event_id = cem.source_event_id
            left join foundation.source_record sr
              on sr.source_record_id = se.source_record_id
            order by ce.event_date, ce.sequence_on_date, ce.canonical_event_id, se.source_event_id
            """
        )
        canonical_member_rows = cursor.fetchall()
        cursor.execute(
            """
            select se.source_event_id,
                   se.event_date::text,
                   se.event_type,
                   se.source_group_hint,
                   se.normalized_payload,
                   sr.source_system,
                   sr.source_type
            from foundation.source_event se
            join foundation.source_record sr
              on sr.source_record_id = se.source_record_id
            where sr.source_system = any(%s)
              and se.normalized_payload ->> 'corroboration_only' = 'true'
            order by se.event_date, se.source_event_id
            """
            ,
            (list(CORROBORATING_SOURCE_SYSTEMS),),
        )
        corroboration_rows = cursor.fetchall()

    event_rows = build_corroboration_report_event_rows(canonical_member_rows)
    corroboration_groups = build_corroboration_candidate_groups(corroboration_rows)
    return reconcile_corroboration_report_event_rows(event_rows, corroboration_groups)


def build_corroboration_report_event_rows(rows: list[tuple[object, ...]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    ordered_ids: list[str] = []
    for row in rows:
        canonical_event_id = str(row[0])
        event_row = grouped.get(canonical_event_id)
        if event_row is None:
            event_row = {
                "canonical_event_id": canonical_event_id,
                "event_date": str(row[1]),
                "event_type": str(row[2]),
                "loaded_source_systems": set(),
                "loaded_source_types": set(),
                "_matching_event_type": canonicalize_corroboration_event_type(str(row[2])),
                "_participant_signature": empty_participant_signature(),
                "_sequence_on_date": int(row[3]),
            }
            grouped[canonical_event_id] = event_row
            ordered_ids.append(canonical_event_id)
        if row[5]:
            event_row["loaded_source_systems"].add(str(row[5]))
        if row[6]:
            event_row["loaded_source_types"].add(str(row[6]))
        merge_participant_signature(
            event_row["_participant_signature"],
            extract_participant_signature(dict(row[7] or {})),
        )

    event_rows: list[dict[str, object]] = []
    for canonical_event_id in ordered_ids:
        event_row = grouped[canonical_event_id]
        event_rows.append(
            {
                "canonical_event_id": str(event_row["canonical_event_id"]),
                "event_date": str(event_row["event_date"]),
                "event_type": str(event_row["event_type"]),
                "loaded_source_systems": sorted(event_row["loaded_source_systems"]),
                "loaded_source_types": sorted(event_row["loaded_source_types"]),
                "_matching_event_type": event_row["_matching_event_type"],
                "_participant_signature": event_row["_participant_signature"],
                "_sequence_on_date": event_row["_sequence_on_date"],
            }
        )
    return event_rows


def build_corroboration_candidate_groups(rows: list[tuple[object, ...]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    ordered_keys: list[tuple[str, str, str]] = []
    for row in rows:
        source_event_id = str(row[0])
        event_date = str(row[1])
        event_type = str(row[2])
        matching_event_type = canonicalize_corroboration_event_type(event_type)
        source_group_hint = str(row[3]) if row[3] is not None else None
        group_key = (
            event_date,
            matching_event_type,
            source_group_hint or source_event_id,
        )
        candidate_group = grouped.get(group_key)
        if candidate_group is None:
            candidate_group = {
                "event_date": event_date,
                "event_type": event_type,
                "_matching_event_type": matching_event_type,
                "_source_event_ids": set(),
                "loaded_source_systems": set(),
                "loaded_source_types": set(),
                "_participant_signature": empty_participant_signature(),
            }
            grouped[group_key] = candidate_group
            ordered_keys.append(group_key)
        candidate_group["_source_event_ids"].add(source_event_id)
        if row[5]:
            candidate_group["loaded_source_systems"].add(str(row[5]))
        if row[6]:
            candidate_group["loaded_source_types"].add(str(row[6]))
        merge_participant_signature(
            candidate_group["_participant_signature"],
            extract_participant_signature(dict(row[4] or {})),
        )

    candidate_groups: list[dict[str, object]] = []
    for key in ordered_keys:
        candidate_group = grouped[key]
        candidate_groups.append(
            {
                "event_date": str(candidate_group["event_date"]),
                "event_type": str(candidate_group["event_type"]),
                "_matching_event_type": candidate_group["_matching_event_type"],
                "_source_event_ids": sorted(candidate_group["_source_event_ids"]),
                "loaded_source_systems": sorted(candidate_group["loaded_source_systems"]),
                "loaded_source_types": sorted(candidate_group["loaded_source_types"]),
                "_participant_signature": candidate_group["_participant_signature"],
            }
        )
    return merge_equivalent_corroboration_candidate_groups(candidate_groups)


def candidate_group_signature_key(candidate_group: dict[str, object]) -> tuple[object, ...]:
    participant_signature = candidate_group.get("_participant_signature", {})
    return (
        str(candidate_group.get("event_date")),
        str(candidate_group.get("_matching_event_type")),
        tuple(sorted(str(value) for value in participant_signature.get("player_names_in", set()))),
        tuple(sorted(str(value) for value in participant_signature.get("player_names_out", set()))),
        tuple(sorted(str(value) for value in participant_signature.get("pick_details_in", set()))),
        tuple(sorted(str(value) for value in participant_signature.get("pick_details_out", set()))),
    )


def merge_equivalent_corroboration_candidate_groups(
    candidate_groups: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], dict[str, object]] = {}
    ordered_keys: list[tuple[object, ...]] = []

    for candidate_group in candidate_groups:
        group_key = candidate_group_signature_key(candidate_group)
        merged_group = grouped.get(group_key)
        if merged_group is None:
            merged_group = {
                "event_date": str(candidate_group["event_date"]),
                "event_type": str(candidate_group["event_type"]),
                "_matching_event_type": str(candidate_group["_matching_event_type"]),
                "_source_event_ids": set(candidate_group.get("_source_event_ids", [])),
                "loaded_source_systems": set(candidate_group.get("loaded_source_systems", [])),
                "loaded_source_types": set(candidate_group.get("loaded_source_types", [])),
                "_participant_signature": {
                    "player_names_in": set(candidate_group["_participant_signature"].get("player_names_in", set())),
                    "player_names_out": set(candidate_group["_participant_signature"].get("player_names_out", set())),
                    "pick_details_in": set(candidate_group["_participant_signature"].get("pick_details_in", set())),
                    "pick_details_out": set(candidate_group["_participant_signature"].get("pick_details_out", set())),
                },
            }
            grouped[group_key] = merged_group
            ordered_keys.append(group_key)
            continue

        merged_group["_source_event_ids"].update(candidate_group.get("_source_event_ids", []))
        merged_group["loaded_source_systems"].update(candidate_group.get("loaded_source_systems", []))
        merged_group["loaded_source_types"].update(candidate_group.get("loaded_source_types", []))

    merged_candidate_groups: list[dict[str, object]] = []
    for group_key in ordered_keys:
        merged_group = grouped[group_key]
        merged_candidate_groups.append(
            {
                "event_date": str(merged_group["event_date"]),
                "event_type": str(merged_group["event_type"]),
                "_matching_event_type": str(merged_group["_matching_event_type"]),
                "_source_event_ids": sorted(merged_group["_source_event_ids"]),
                "loaded_source_systems": sorted(merged_group["loaded_source_systems"]),
                "loaded_source_types": sorted(merged_group["loaded_source_types"]),
                "_participant_signature": merged_group["_participant_signature"],
            }
        )
    return merged_candidate_groups


def reconcile_corroboration_report_event_rows(
    event_rows: list[dict[str, object]],
    candidate_groups: list[dict[str, object]],
) -> list[dict[str, object]]:
    event_rows_by_id = {
        str(event_row["canonical_event_id"]): {
            **event_row,
            "_loaded_source_systems_set": set(event_row.get("loaded_source_systems", [])),
            "_loaded_source_types_set": set(event_row.get("loaded_source_types", [])),
        }
        for event_row in event_rows
    }
    candidate_indexes_by_event_id: dict[str, list[int]] = defaultdict(list)
    event_ids_by_candidate_index: dict[int, list[str]] = defaultdict(list)

    for candidate_index, candidate_group in enumerate(candidate_groups):
        for event_row in event_rows:
            if corroboration_candidate_confidently_matches_event(candidate_group, event_row):
                canonical_event_id = str(event_row["canonical_event_id"])
                candidate_indexes_by_event_id[canonical_event_id].append(candidate_index)
                event_ids_by_candidate_index[candidate_index].append(canonical_event_id)

    matched_candidate_indexes: set[int] = set()
    for canonical_event_id, candidate_indexes in candidate_indexes_by_event_id.items():
        eligible_candidate_indexes = [
            candidate_index
            for candidate_index in candidate_indexes
            if event_ids_by_candidate_index.get(candidate_index) == [canonical_event_id]
        ]
        if not eligible_candidate_indexes:
            continue
        event_row = event_rows_by_id[canonical_event_id]
        merge_reconciled_candidate_groups_into_event_row(
            event_row,
            [candidate_groups[candidate_index] for candidate_index in eligible_candidate_indexes],
            [
                f"Audit-time reconciliation matched corroboration-only rows from {describe_candidate_group_source_systems([candidate_groups[candidate_index] for candidate_index in eligible_candidate_indexes])} to this canonical event with no participant mismatch detected."
            ],
        )
        matched_candidate_indexes.update(eligible_candidate_indexes)

    reconcile_grouped_trade_candidates(
        event_rows=event_rows,
        event_rows_by_id=event_rows_by_id,
        candidate_groups=candidate_groups,
        matched_candidate_indexes=matched_candidate_indexes,
    )
    reconcile_nearby_signing_and_waiver_candidates(
        event_rows=event_rows,
        event_rows_by_id=event_rows_by_id,
        candidate_groups=candidate_groups,
        matched_candidate_indexes=matched_candidate_indexes,
        max_day_delta=AUDIT_NEAR_DATE_RECONCILIATION_WINDOW_DAYS,
    )

    for event_row in event_rows_by_id.values():
        if event_row.get("_reconciled_conflict_status") == "no_conflict_detected":
            continue
        conflicting_candidates = [
            candidate_groups[index]
            for index in range(len(candidate_groups))
            if index not in matched_candidate_indexes
            and corroboration_candidate_conflicts_with_event(candidate_groups[index], event_row)
        ]
        if len(conflicting_candidates) == 1:
            candidate_group = conflicting_candidates[0]
            event_row["_reconciled_conflict_status"] = "conflict_suspected"
            event_row["_reconciliation_notes"] = [
                f"Loaded corroboration rows from {describe_candidate_group_source_systems([candidate_group])} share the event date/type and participant overlap for this canonical event, but the directional participant details do not fully align."
            ]
            event_row["_conflicting_source_event_ids"] = candidate_group["_source_event_ids"]

    reconciled_rows: list[dict[str, object]] = []
    for event_row in event_rows:
        reconciled = dict(event_rows_by_id[str(event_row["canonical_event_id"])])
        reconciled["loaded_source_systems"] = sorted(reconciled.pop("_loaded_source_systems_set"))
        reconciled["loaded_source_types"] = sorted(reconciled.pop("_loaded_source_types_set"))
        reconciled_rows.append(reconciled)
    return reconciled_rows


def merge_reconciled_candidate_groups_into_event_row(
    event_row: dict[str, object],
    candidate_groups: list[dict[str, object]],
    notes: list[str],
) -> None:
    for candidate_group in candidate_groups:
        event_row["_loaded_source_systems_set"].update(candidate_group["loaded_source_systems"])
        event_row["_loaded_source_types_set"].update(candidate_group["loaded_source_types"])
    event_row["_reconciled_conflict_status"] = "no_conflict_detected"
    event_row["_reconciliation_notes"] = notes


def describe_candidate_group_source_systems(candidate_groups: list[dict[str, object]]) -> str:
    source_systems = sorted(
        {
            str(source_system)
            for candidate_group in candidate_groups
            for source_system in candidate_group.get("loaded_source_systems", [])
            if source_system
        }
    )
    if not source_systems:
        return "corroborating source systems"
    return ", ".join(source_systems)


def reconcile_grouped_trade_candidates(
    *,
    event_rows: list[dict[str, object]],
    event_rows_by_id: dict[str, dict[str, object]],
    candidate_groups: list[dict[str, object]],
    matched_candidate_indexes: set[int],
) -> None:
    combo_indexes_by_event_id: dict[str, list[tuple[int, ...]]] = defaultdict(list)
    event_ids_by_combo_indexes: dict[tuple[int, ...], list[str]] = defaultdict(list)

    for event_row in event_rows:
        canonical_event_id = str(event_row["canonical_event_id"])
        if event_row.get("_matching_event_type") != "trade":
            continue
        if event_rows_by_id[canonical_event_id].get("_reconciled_conflict_status") == "no_conflict_detected":
            continue
        candidate_indexes = [
            candidate_index
            for candidate_index, candidate_group in enumerate(candidate_groups)
            if candidate_index not in matched_candidate_indexes
            and corroboration_candidate_conflicts_with_event(candidate_group, event_row)
        ]
        if len(candidate_indexes) < 2:
            continue
        candidate_indexes = candidate_indexes[:AUDIT_MAX_TRADE_MATCH_COMBINATION_SIZE]
        matching_combos: list[tuple[int, ...]] = []
        for combo_size in range(2, len(candidate_indexes) + 1):
            for combo_indexes in combinations(candidate_indexes, combo_size):
                combo_groups = [candidate_groups[index] for index in combo_indexes]
                if not corroboration_candidate_groups_confidently_match_trade_event(combo_groups, event_row):
                    continue
                matching_combos.append(combo_indexes)
        if len(matching_combos) != 1:
            continue
        combo_indexes_by_event_id[canonical_event_id].append(matching_combos[0])
        event_ids_by_combo_indexes[matching_combos[0]].append(canonical_event_id)

    for canonical_event_id, combos in combo_indexes_by_event_id.items():
        if len(combos) != 1:
            continue
        combo_indexes = combos[0]
        if event_ids_by_combo_indexes.get(combo_indexes) != [canonical_event_id]:
            continue
        merge_reconciled_candidate_groups_into_event_row(
            event_rows_by_id[canonical_event_id],
            [candidate_groups[index] for index in combo_indexes],
            [
                f"Audit-time reconciliation matched grouped same-day corroboration-only trade rows from {describe_candidate_group_source_systems([candidate_groups[index] for index in combo_indexes])} to this canonical event with no participant mismatch detected."
            ],
        )
        matched_candidate_indexes.update(combo_indexes)


def reconcile_nearby_signing_and_waiver_candidates(
    *,
    event_rows: list[dict[str, object]],
    event_rows_by_id: dict[str, dict[str, object]],
    candidate_groups: list[dict[str, object]],
    matched_candidate_indexes: set[int],
    max_day_delta: int,
) -> None:
    candidate_indexes_by_event_id: dict[str, list[int]] = defaultdict(list)
    event_ids_by_candidate_index: dict[int, list[str]] = defaultdict(list)
    nearby_day_delta_by_match: dict[tuple[str, int], int] = {}

    for candidate_index, candidate_group in enumerate(candidate_groups):
        if candidate_index in matched_candidate_indexes:
            continue
        if candidate_group.get("_matching_event_type") not in {"signing", "waiver"}:
            continue
        for event_row in event_rows:
            canonical_event_id = str(event_row["canonical_event_id"])
            if event_rows_by_id[canonical_event_id].get("_reconciled_conflict_status") == "no_conflict_detected":
                continue
            if not corroboration_candidate_confidently_matches_event_within_window(
                candidate_group,
                event_row,
                max_day_delta=max_day_delta,
            ):
                continue
            candidate_indexes_by_event_id[canonical_event_id].append(candidate_index)
            event_ids_by_candidate_index[candidate_index].append(canonical_event_id)
            nearby_day_delta_by_match[(canonical_event_id, candidate_index)] = abs(
                corroboration_candidate_day_delta(candidate_group, event_row) or 0
            )

    for candidate_index, event_ids in event_ids_by_candidate_index.items():
        if len(event_ids) != 1:
            continue
        canonical_event_id = event_ids[0]
        if candidate_indexes_by_event_id.get(canonical_event_id) != [candidate_index]:
            continue
        day_delta = nearby_day_delta_by_match[(canonical_event_id, candidate_index)]
        day_label = "day" if day_delta == 1 else "days"
        merge_reconciled_candidate_groups_into_event_row(
            event_rows_by_id[canonical_event_id],
            [candidate_groups[candidate_index]],
            [
                f"Audit-time reconciliation matched a corroboration-only row from {describe_candidate_group_source_systems([candidate_groups[candidate_index]])} to this canonical signing/waiver event with no participant mismatch detected.",
                f"The corroborating source row is offset by {day_delta} {day_label} from the canonical event date.",
            ],
        )
        matched_candidate_indexes.add(candidate_index)


def canonicalize_corroboration_event_type(event_type: str) -> str:
    normalized = event_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"trade", "draft", "waiver", "signing"}:
        return normalized
    if normalized in {
        "re_signing",
        "resigning",
        "extension",
        "conversion",
        "10_day",
        "ten_day",
        "ten_day_signing",
        "two_way",
        "two_way_signing",
        "two_way_conversion",
    }:
        return "signing"
    if normalized in {"release", "released", "waived"}:
        return "waiver"
    return normalized


def parse_iso_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def empty_participant_signature() -> dict[str, set[str]]:
    return {
        "player_names_in": set(),
        "player_names_out": set(),
        "pick_details_in": set(),
        "pick_details_out": set(),
    }


def extract_participant_signature(payload: dict[str, object]) -> dict[str, set[str]]:
    signature = empty_participant_signature()
    for key in ("player_names_in", "player_names_out"):
        for value in payload.get(key, []):
            if isinstance(value, str) and value.strip():
                signature[key].add(normalize_player_alias_name(value))
    for key in ("pick_details_in", "pick_details_out"):
        for detail in payload.get(key, []):
            if not isinstance(detail, dict):
                continue
            raw_text = detail.get("raw_text")
            if isinstance(raw_text, str) and raw_text.strip():
                signature[key].add(raw_text.strip().lower())
    return signature


def merge_participant_signature(
    target: dict[str, set[str]],
    source: dict[str, set[str]],
) -> None:
    for key in target:
        target[key].update(source.get(key, set()))


def audit_player_name_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", normalize_player_alias_name(value))
    ascii_folded = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = [token for token in ascii_folded.split(" ") if token]
    while tokens and tokens[-1] in AUDIT_PLAYER_SUFFIX_TOKENS:
        tokens.pop()
    return tuple(tokens)


def audit_player_first_names_equivalent(left: str, right: str) -> bool:
    if left == right:
        return True
    return right in AUDIT_SAFE_FIRST_NAME_VARIANTS.get(left, frozenset())


def audit_player_names_equivalent(left: str, right: str) -> bool:
    if left == right:
        return True

    left_tokens = audit_player_name_tokens(left)
    right_tokens = audit_player_name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    if len(left_tokens) != len(right_tokens):
        return False
    if len(left_tokens) < 2:
        return False

    return left_tokens[1:] == right_tokens[1:] and audit_player_first_names_equivalent(
        left_tokens[0],
        right_tokens[0],
    )


def audit_player_name_sets_equivalent(left: set[str], right: set[str]) -> bool:
    if len(left) != len(right):
        return False
    if left == right:
        return True
    if not left:
        return True

    left_names = tuple(sorted(left))
    right_names = tuple(sorted(right))

    def match_name(index: int, remaining: tuple[str, ...]) -> bool:
        if index == len(left_names):
            return True
        for remaining_index, right_name in enumerate(remaining):
            if not audit_player_names_equivalent(left_names[index], right_name):
                continue
            next_remaining = remaining[:remaining_index] + remaining[remaining_index + 1 :]
            if match_name(index + 1, next_remaining):
                return True
        return False

    return match_name(0, right_names)


def audit_player_name_sets_overlap(left: set[str], right: set[str]) -> bool:
    return any(
        audit_player_names_equivalent(left_name, right_name)
        for left_name in left
        for right_name in right
    )


def corroboration_candidate_confidently_matches_event(
    candidate_group: dict[str, object],
    event_row: dict[str, object],
) -> bool:
    return (
        corroboration_candidate_day_delta(candidate_group, event_row) == 0
        and corroboration_candidate_exact_participant_match(candidate_group, event_row)
    )


def corroboration_candidate_confidently_matches_event_within_window(
    candidate_group: dict[str, object],
    event_row: dict[str, object],
    *,
    max_day_delta: int,
) -> bool:
    if candidate_group.get("_matching_event_type") not in {"signing", "waiver"}:
        return False
    day_delta = corroboration_candidate_day_delta(candidate_group, event_row)
    if day_delta is None or day_delta == 0 or abs(day_delta) > max_day_delta:
        return False
    return corroboration_candidate_exact_participant_match(candidate_group, event_row)


def corroboration_candidate_day_delta(
    candidate_group: dict[str, object],
    event_row: dict[str, object],
) -> int | None:
    if str(candidate_group.get("_matching_event_type")) != str(event_row.get("_matching_event_type")):
        return None
    candidate_date = parse_iso_date(candidate_group.get("event_date"))
    event_date = parse_iso_date(event_row.get("event_date"))
    if candidate_date is None or event_date is None:
        return None
    return (candidate_date - event_date).days


def corroboration_candidate_exact_participant_match(
    candidate_group: dict[str, object],
    event_row: dict[str, object],
) -> bool:
    if str(candidate_group.get("_matching_event_type")) != str(event_row.get("_matching_event_type")):
        return False

    candidate_signature = candidate_group.get("_participant_signature", {})
    event_signature = event_row.get("_participant_signature", {})
    candidate_inbound = set(candidate_signature.get("player_names_in", set()))
    candidate_outbound = set(candidate_signature.get("player_names_out", set()))
    event_inbound = set(event_signature.get("player_names_in", set()))
    event_outbound = set(event_signature.get("player_names_out", set()))

    if not candidate_inbound and not candidate_outbound:
        return False

    event_type = str(candidate_group.get("_matching_event_type"))
    if event_type == "trade":
        inbound_matches = (
            audit_player_name_sets_equivalent(candidate_inbound, event_inbound)
            if candidate_inbound
            else True
        )
        outbound_matches = (
            audit_player_name_sets_equivalent(candidate_outbound, event_outbound)
            if candidate_outbound
            else True
        )
        return inbound_matches and outbound_matches and bool(candidate_inbound or candidate_outbound)

    if event_type == "waiver":
        return (
            not candidate_inbound
            and not event_inbound
            and audit_player_name_sets_equivalent(candidate_outbound, event_outbound)
        )

    if event_type == "signing":
        return (
            not candidate_outbound
            and not event_outbound
            and audit_player_name_sets_equivalent(candidate_inbound, event_inbound)
        )

    return False


def corroboration_candidate_groups_confidently_match_trade_event(
    candidate_groups: list[dict[str, object]],
    event_row: dict[str, object],
) -> bool:
    if not candidate_groups or str(event_row.get("_matching_event_type")) != "trade":
        return False
    if any(corroboration_candidate_day_delta(candidate_group, event_row) != 0 for candidate_group in candidate_groups):
        return False

    combined_signature = empty_participant_signature()
    for candidate_group in candidate_groups:
        merge_participant_signature(
            combined_signature,
            candidate_group.get("_participant_signature", {}),
        )
    return corroboration_candidate_exact_participant_match(
        {
            "_matching_event_type": "trade",
            "_participant_signature": combined_signature,
        },
        event_row,
    )


def corroboration_candidate_conflicts_with_event(
    candidate_group: dict[str, object],
    event_row: dict[str, object],
) -> bool:
    if str(candidate_group.get("event_date")) != str(event_row.get("event_date")):
        return False
    if str(candidate_group.get("_matching_event_type")) != str(event_row.get("_matching_event_type")):
        return False
    if corroboration_candidate_confidently_matches_event(candidate_group, event_row):
        return False

    candidate_signature = candidate_group.get("_participant_signature", {})
    event_signature = event_row.get("_participant_signature", {})
    candidate_players = set(candidate_signature.get("player_names_in", set())) | set(
        candidate_signature.get("player_names_out", set())
    )
    event_players = set(event_signature.get("player_names_in", set())) | set(
        event_signature.get("player_names_out", set())
    )
    return bool(candidate_players and event_players and audit_player_name_sets_overlap(candidate_players, event_players))


def fetch_alias_metrics(connection: psycopg.Connection) -> dict[str, object]:
    if not table_exists(connection, "player_alias"):
        return {"count": 0, "manual_count": 0, "sample": []}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select count(*),
                   count(*) filter (where is_manual)
            from foundation.player_alias
            """
        )
        count_row = cursor.fetchone()
        cursor.execute(
            """
            select alias_name, player_id, source_system, is_manual
            from foundation.player_alias
            order by is_manual desc, alias_name
            limit 25
            """
        )
        sample_rows = cursor.fetchall()
    return {
        "count": int(count_row[0]),
        "manual_count": int(count_row[1]),
        "sample": [
            {
                "alias_name": str(row[0]),
                "player_id": str(row[1]),
                "source_system": str(row[2]),
                "is_manual": bool(row[3]),
            }
            for row in sample_rows
        ],
    }


def fetch_snapshot_metrics(connection: psycopg.Connection) -> dict[str, object]:
    if not table_exists(connection, "roster_snapshot"):
        return {
            "snapshots": 0,
            "player_rows": 0,
            "pick_rows": 0,
            "assetless_player_rows": 0,
            "by_kind": [],
            "by_season": [],
            "contract_status": [],
            "date_aware_reconstruction": 0,
            "derived_from_roster_baseline": 0,
        }

    with connection.cursor() as cursor:
        cursor.execute("select count(*) from foundation.roster_snapshot")
        snapshot_count = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from foundation.roster_snapshot_player")
        player_rows = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from foundation.roster_snapshot_pick")
        pick_rows = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from foundation.roster_snapshot_player where asset_id is null")
        assetless_player_rows = int(cursor.fetchone()[0])
        cursor.execute(
            """
            select snapshot_kind, count(*)
            from foundation.roster_snapshot
            group by snapshot_kind
            order by snapshot_kind
            """
        )
        kind_rows = cursor.fetchall()
        cursor.execute(
            """
            select season, count(*)
            from foundation.roster_snapshot
            group by season
            order by season
            """
        )
        season_rows = cursor.fetchall()
        cursor.execute(
            """
            select roster_status,
                   count(*),
                   count(*) filter (where is_two_way),
                   count(*) filter (where is_standard_contract)
            from foundation.roster_snapshot_player
            group by roster_status
            order by roster_status
            """
        )
        contract_rows = cursor.fetchall()
        cursor.execute(
            """
            select count(*)
            from foundation.roster_snapshot
            where coalesce(notes, '') ilike '%Date-aware reconstruction%'
            """
        )
        date_aware_count = int(cursor.fetchone()[0])
        cursor.execute(
            """
            select count(*)
            from foundation.roster_snapshot
            where (
                coalesce(notes, '') ilike '%roster baseline%'
                or coalesce(notes, '') ilike '%not a date-exact%'
            )
              and coalesce(notes, '') not ilike '%Date-aware reconstruction%'
            """
        )
        derived_count = int(cursor.fetchone()[0])

    return {
        "snapshots": snapshot_count,
        "player_rows": player_rows,
        "pick_rows": pick_rows,
        "assetless_player_rows": assetless_player_rows,
        "by_kind": [{"snapshot_kind": str(row[0]), "count": int(row[1])} for row in kind_rows],
        "by_season": [{"season": str(row[0]), "count": int(row[1])} for row in season_rows],
        "contract_status": [
            {
                "roster_status": str(row[0]),
                "rows": int(row[1]),
                "two_way_rows": int(row[2]),
                "standard_contract_rows": int(row[3]),
            }
            for row in contract_rows
        ],
        "date_aware_reconstruction": date_aware_count,
        "derived_from_roster_baseline": derived_count,
    }


def fetch_pick_inventory_metrics(connection: psycopg.Connection) -> dict[str, object]:
    if not table_exists(connection, "pick_inventory_obligation"):
        return {
            "obligations": 0,
            "loadable_rows": 0,
            "documented_only_rows": 0,
            "uncertain_rows": 0,
            "unknown_owner_rows": 0,
            "rows_missing_source_event": 0,
            "by_holding_status": [],
            "by_confidence": [],
            "unknown_owner_samples": [],
            "non_loadable_samples": [],
        }

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select count(*),
                   count(*) filter (where loadable),
                   count(*) filter (where not loadable),
                   count(*) filter (where confidence = 'uncertain'),
                   count(*) filter (where owner_team_code = 'UNKNOWN'),
                   count(*) filter (where source_event_id is null and canonical_event_id is null)
            from foundation.pick_inventory_obligation
            """
        )
        count_row = cursor.fetchone()
        cursor.execute(
            """
            select holding_status, count(*)
            from foundation.pick_inventory_obligation
            group by holding_status
            order by holding_status
            """
        )
        holding_rows = cursor.fetchall()
        cursor.execute(
            """
            select confidence, count(*)
            from foundation.pick_inventory_obligation
            group by confidence
            order by confidence
            """
        )
        confidence_rows = cursor.fetchall()
        cursor.execute(
            """
            select obligation_id, draft_year, round_number, direction, holding_status, owner_team_code
            from foundation.pick_inventory_obligation
            where owner_team_code = 'UNKNOWN'
            order by obligation_id
            limit 25
            """
        )
        unknown_owner_rows = cursor.fetchall()
        cursor.execute(
            """
            select obligation_id, draft_year, round_number, direction, holding_status, confidence, notes
            from foundation.pick_inventory_obligation
            where not loadable
            order by obligation_id
            limit 25
            """
        )
        non_loadable_rows = cursor.fetchall()

    return {
        "obligations": int(count_row[0]),
        "loadable_rows": int(count_row[1]),
        "documented_only_rows": int(count_row[2]),
        "uncertain_rows": int(count_row[3]),
        "unknown_owner_rows": int(count_row[4]),
        "rows_missing_source_event": int(count_row[5]),
        "by_holding_status": [{"holding_status": str(row[0]), "rows": int(row[1])} for row in holding_rows],
        "by_confidence": [{"confidence": str(row[0]), "rows": int(row[1])} for row in confidence_rows],
        "unknown_owner_samples": [
            {
                "obligation_id": str(row[0]),
                "draft_year": int(row[1]),
                "round_number": int(row[2]),
                "direction": str(row[3]),
                "holding_status": str(row[4]),
                "owner_team_code": str(row[5]),
            }
            for row in unknown_owner_rows
        ],
        "non_loadable_samples": [
            {
                "obligation_id": str(row[0]),
                "draft_year": int(row[1]),
                "round_number": int(row[2]),
                "direction": str(row[3]),
                "holding_status": str(row[4]),
                "confidence": str(row[5]),
                "notes": str(row[6]) if row[6] is not None else None,
            }
            for row in non_loadable_rows
        ],
    }


def fetch_draft_metrics(connection: psycopg.Connection) -> dict[str, object]:
    lottery_results = 0
    lottery_results_with_owner_original = 0
    if table_exists(connection, "draft_lottery_result"):
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from foundation.draft_lottery_result")
            lottery_results = int(cursor.fetchone()[0])
            cursor.execute(
                """
                select count(*)
                from foundation.draft_lottery_result
                where owner_team_code is not null
                  and original_team_code is not null
                """
            )
            lottery_results_with_owner_original = int(cursor.fetchone()[0])

    if not table_exists(connection, "draft_selection"):
        return {
            "selections": 0,
            "unlinked_pick_rows": 0,
            "resolved_pick_rows": 0,
            "unlinked_source_event_rows": 0,
            "lottery_results": lottery_results,
            "lottery_results_with_owner_original": lottery_results_with_owner_original,
            "by_year": [],
        }
    with connection.cursor() as cursor:
        cursor.execute("select count(*) from foundation.draft_selection")
        selections = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from foundation.draft_selection where pick_id is null")
        unlinked_pick_rows = int(cursor.fetchone()[0])
        resolved_pick_rows = 0
        if table_exists(connection, "draft_pick_resolution"):
            cursor.execute("select count(*) from foundation.draft_pick_resolution")
            resolved_pick_rows = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from foundation.draft_selection where source_event_id is null")
        unlinked_source_event_rows = int(cursor.fetchone()[0])
        cursor.execute(
            """
            select draft_year, count(*)
            from foundation.draft_selection
            group by draft_year
            order by draft_year
            """
        )
        year_rows = cursor.fetchall()
    return {
        "selections": selections,
        "unlinked_pick_rows": unlinked_pick_rows,
        "resolved_pick_rows": resolved_pick_rows,
        "unlinked_source_event_rows": unlinked_source_event_rows,
        "lottery_results": lottery_results,
        "lottery_results_with_owner_original": lottery_results_with_owner_original,
        "by_year": [{"draft_year": int(row[0]), "selections": int(row[1])} for row in year_rows],
    }


def build_event_span_currentness(event_span: dict[str, object]) -> dict[str, object]:
    loaded_end_date = event_span.get("end_date")
    if loaded_end_date == CURRENTNESS_LAST_VERIFIED_EVENT_DATE:
        status = "verified_quiet_interval"
        evidence = (
            "Loaded canonical/source event end date matches the last verified Memphis roster event; "
            f"no later public Memphis roster event was verified through {CURRENTNESS_VERIFIED_THROUGH}."
        )
    elif loaded_end_date and str(loaded_end_date) > CURRENTNESS_LAST_VERIFIED_EVENT_DATE:
        status = "extends_beyond_verified_basis"
        evidence = (
            "Loaded data extends beyond the current manually verified basis; refresh the currentness "
            "source review before treating the later end date as audited."
        )
    else:
        status = "behind_verified_last_event"
        evidence = (
            f"Loaded event end date is {loaded_end_date}; the last verified Memphis roster event is "
            f"{CURRENTNESS_LAST_VERIFIED_EVENT_DATE}."
        )

    return {
        "status": status,
        "loaded_event_end_date": loaded_end_date,
        "last_verified_event_date": CURRENTNESS_LAST_VERIFIED_EVENT_DATE,
        "verified_through": CURRENTNESS_VERIFIED_THROUGH,
        "source_basis": list(CURRENTNESS_SOURCE_BASIS),
        "evidence": evidence,
        "limitation": "Currentness is a dated source review, not proof against future or unpublished transaction records.",
    }


def build_source_coverage_report(source_coverage: list[object]) -> dict[str, object]:
    systems = sorted(
        {
            str(row.get("source_system"))
            for row in source_coverage
            if isinstance(row, dict) and row.get("source_system")
        }
    )
    has_bref = "basketball_reference" in systems
    corrob_source_systems = sorted(
        {
            source_system
            for policy in SOURCE_POLICY.provider_roles
            if policy.role != "chronology_spine"
            for source_system in policy.source_systems
            if source_system != "basketball_reference"
        }
    )
    has_official_reference = any(system in systems for system in corrob_source_systems)
    gaps: list[dict[str, str]] = []
    if not has_bref:
        gaps.append(
            build_gap(
                "high",
                "Basketball-Reference transaction source coverage is absent.",
                "No source_record rows report source_system=basketball_reference.",
                "Load the checked-in Basketball-Reference source-event path before relying on transaction spans.",
            )
        )
    if not has_official_reference:
        gaps.append(
            build_gap(
                "medium",
                "Official or corroborating source coverage is not systematic in loaded records.",
                f"Loaded source systems: {', '.join(systems) if systems else 'none'}.",
                "Add NBA Stats, NBA.com, or team-official source records where they are needed for identity/currentness corroboration.",
            )
        )
    return {
        "loaded_source_systems": systems,
        "has_basketball_reference": has_bref,
        "has_official_or_corrob_source": has_official_reference,
        "gaps": gaps,
    }


def build_source_corroboration_report(event_rows: list[dict[str, object]]) -> dict[str, object]:
    events = [build_source_corroboration_event(row) for row in event_rows]
    return {
        "policy_version": SOURCE_POLICY_VERSION,
        "summary": build_source_corroboration_summary(events),
        "events": events,
    }


def build_source_corroboration_event(row: dict[str, object]) -> dict[str, object]:
    fact_type = infer_corroboration_fact_type(str(row.get("event_type") or ""))
    fact_policy = {
        policy.fact_type: policy
        for policy in SOURCE_POLICY.first_pass_fact_types
    }.get(fact_type)
    loaded_source_systems = sorted(
        {
            str(system)
            for system in row.get("loaded_source_systems", [])
            if system
        }
    )
    loaded_source_types = sorted(
        {
            str(source_type)
            for source_type in row.get("loaded_source_types", [])
            if source_type
        }
    )
    recognized_provider_roles = (
        list(dict.fromkeys([*fact_policy.minimum_required_roles, *fact_policy.target_roles]))
        if fact_policy
        else []
    )
    required_source_roles = list(fact_policy.minimum_required_roles) if fact_policy else []
    target_roles = list(fact_policy.target_roles) if fact_policy else []
    loaded_roles = roles_supported_by_source_systems(loaded_source_systems)
    missing_roles = [
        role
        for role in required_source_roles
        if role not in loaded_roles
    ]
    evidence_states = build_evidence_states(
        recognized_provider_roles=recognized_provider_roles,
        required_source_roles=required_source_roles,
        loaded_roles=loaded_roles,
        loaded_source_systems=loaded_source_systems,
    )
    corroboration_status = classify_corroboration_status(
        fact_type=fact_type,
        missing_roles=missing_roles,
        loaded_source_systems=loaded_source_systems,
        target_roles=target_roles,
        loaded_roles=loaded_roles,
        recognized_provider_roles=recognized_provider_roles,
    )
    conflict_status = str(row.get("_reconciled_conflict_status") or "not_evaluated")
    notes = build_source_corroboration_notes(
        corroboration_status=corroboration_status,
        conflict_status=conflict_status,
        missing_roles=missing_roles,
        loaded_source_systems=loaded_source_systems,
        target_roles=target_roles,
        loaded_roles=loaded_roles,
        reconciliation_notes=[
            str(note)
            for note in row.get("_reconciliation_notes", [])
            if isinstance(note, str) and note.strip()
        ],
    )

    return {
        "canonical_event_id": str(row.get("canonical_event_id") or ""),
        "event_date": str(row.get("event_date") or ""),
        "event_type": str(row.get("event_type") or ""),
        "fact_type": fact_type,
        "loaded_source_systems": loaded_source_systems,
        "loaded_source_types": loaded_source_types,
        "recognized_provider_roles": recognized_provider_roles,
        "required_source_roles": required_source_roles,
        "missing_roles": missing_roles,
        "evidence_states": evidence_states,
        "corroboration_status": corroboration_status,
        "conflict_status": conflict_status,
        "notes": notes,
    }


def infer_corroboration_fact_type(event_type: str) -> str:
    normalized = event_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {
        "trade",
        "signing",
        "re_signing",
        "resigning",
        "extension",
        "waiver",
        "waived",
        "release",
        "released",
        "10_day",
        "ten_day",
        "ten_day_signing",
        "conversion",
        "two_way",
        "two_way_signing",
        "two_way_conversion",
    }:
        return "player_movement"
    if normalized in {
        "draft",
        "draft_pick",
        "draft_selection",
        "pick",
        "pick_right",
        "pick_right_detail",
        "pick_conveyance",
        "pick_swap",
        "lottery",
        "draft_lottery",
    }:
        return "pick_right_detail"
    if normalized in {"roster", "roster_snapshot", "team_roster", "common_team_roster"}:
        return "roster_snapshot"
    if normalized in {"player", "player_identity", "player_reference", "identity"}:
        return "player_identity"
    if normalized in {"transaction", "transaction_chronology"}:
        return "transaction_chronology"
    return "out_of_scope"


def roles_supported_by_source_systems(source_systems: list[str]) -> set[str]:
    loaded_systems = set(source_systems)
    return {
        policy.role
        for policy in SOURCE_POLICY.provider_roles
        if loaded_systems.intersection(policy.source_systems)
    }


def source_systems_for_roles(roles: list[str]) -> set[str]:
    requested_roles = set(roles)
    systems: set[str] = set()
    for policy in SOURCE_POLICY.provider_roles:
        if policy.role in requested_roles:
            systems.update(policy.source_systems)
    return systems


def build_evidence_states(
    *,
    recognized_provider_roles: list[str],
    required_source_roles: list[str],
    loaded_roles: set[str],
    loaded_source_systems: list[str],
) -> list[dict[str, object]]:
    states: list[dict[str, object]] = []
    for role in recognized_provider_roles:
        if role in loaded_roles:
            state = "supports_event"
        elif role in required_source_roles:
            state = "missing_required_evidence"
        else:
            state = "recognized_provider"
        states.append(
            {
                "role": role,
                "state": state,
                "loaded_source_systems": sorted(
                    set(loaded_source_systems).intersection(source_systems_for_roles([role]))
                ),
            }
        )
    return states


def classify_corroboration_status(
    *,
    fact_type: str,
    missing_roles: list[str],
    loaded_source_systems: list[str],
    target_roles: list[str],
    loaded_roles: set[str],
    recognized_provider_roles: list[str],
) -> str:
    if fact_type not in {policy.fact_type for policy in SOURCE_POLICY.first_pass_fact_types}:
        return "out_of_scope"
    if missing_roles:
        return "missing_required_evidence"
    non_bref_target_systems = {
        system
        for system in source_systems_for_roles(target_roles)
        if system != "basketball_reference"
    }
    if set(loaded_source_systems) == {"basketball_reference"} and not set(loaded_source_systems).intersection(
        non_bref_target_systems
    ):
        return "bref_only"
    if any(role not in loaded_roles for role in recognized_provider_roles):
        return "recognized_provider_not_loaded"
    return "meets_minimum"


def build_source_corroboration_notes(
    *,
    corroboration_status: str,
    conflict_status: str,
    missing_roles: list[str],
    loaded_source_systems: list[str],
    target_roles: list[str],
    loaded_roles: set[str],
    reconciliation_notes: list[str],
) -> list[str]:
    notes: list[str] = list(reconciliation_notes)
    if missing_roles:
        notes.append(f"Missing required source roles: {', '.join(missing_roles)}.")
    if corroboration_status == "bref_only":
        notes.append(
            "Loaded evidence for this canonical event is Basketball-Reference only; target non-BRef providers are recognized but not loaded for the event."
        )
    elif corroboration_status == "recognized_provider_not_loaded":
        unloaded_targets = [role for role in target_roles if role not in loaded_roles]
        if unloaded_targets:
            notes.append(
                f"Recognized target provider roles are not loaded for this event: {', '.join(unloaded_targets)}."
            )
    if conflict_status == "not_evaluated" and "structured_player_movement" in target_roles:
        notes.append(
            "No confident audit-time reconciliation to corroboration-only corroborating source rows was found for this canonical event."
        )
    if not loaded_source_systems:
        notes.append("No loaded source records are attached through canonical event membership.")
    notes.append(SOURCE_POLICY.planned_vs_loaded_rule)
    return notes


def build_source_corroboration_summary(events: list[dict[str, object]]) -> dict[str, object]:
    by_corroboration_status: dict[str, int] = {}
    by_conflict_status: dict[str, int] = {}
    for event in events:
        corroboration_status = str(event.get("corroboration_status"))
        by_corroboration_status[corroboration_status] = by_corroboration_status.get(corroboration_status, 0) + 1
        conflict_status = str(event.get("conflict_status"))
        by_conflict_status[conflict_status] = by_conflict_status.get(conflict_status, 0) + 1

    return {
        "reporting_unit": CORROBORATION_REPORTING_UNIT,
        "derivation": (
            f"{CORROBORATION_DERIVATION_PATH} + audit-time reconciliation of "
            "corroboration_only source_event rows from loaded corroborating source systems"
        ),
        "event_fields": list(CORROBORATION_REPORT_EVENT_FIELDS),
        "total_events": len(events),
        "by_corroboration_status": dict(sorted(by_corroboration_status.items())),
        "by_conflict_status": dict(sorted(by_conflict_status.items())),
        "bref_only_events": by_corroboration_status.get("bref_only", 0),
        "missing_required_events": by_corroboration_status.get("missing_required_evidence", 0),
        "planned_vs_loaded_rule": SOURCE_POLICY.planned_vs_loaded_rule,
    }


def build_pick_inventory_fixture_gap_report(fixture_path: Path) -> dict[str, object]:
    fixture = load_pick_inventory_fixture(fixture_path)
    non_loadable_rows = [row for row in fixture.rows if not row.loadable]
    unknown_owner_rows = [row for row in fixture.rows if row.owner_team_code == "UNKNOWN"]
    return {
        "fixture_path": str(fixture_path),
        "fixture_rows": len(fixture.rows),
        "loadable_rows": sum(1 for row in fixture.rows if row.loadable),
        "non_loadable_rows": len(non_loadable_rows),
        "unknown_owner_rows": len(unknown_owner_rows),
        "non_loadable_samples": [
            {
                "obligation_id": row.obligation_id,
                "draft_year": row.draft_year,
                "round_number": row.round_number,
                "direction": row.direction,
                "holding_status": row.holding_status,
                "obligation_type": row.obligation_type,
                "confidence": row.confidence,
                "notes": row.notes,
            }
            for row in non_loadable_rows[:25]
        ],
        "unknown_owner_samples": [
            {
                "obligation_id": row.obligation_id,
                "draft_year": row.draft_year,
                "round_number": row.round_number,
                "direction": row.direction,
                "holding_status": row.holding_status,
                "owner_team_code": row.owner_team_code,
                "notes": row.notes,
            }
            for row in unknown_owner_rows[:25]
        ],
        "limitation": "Non-loadable fixture rows document conditional fallbacks and are intentionally excluded from DB loads and snapshot projection.",
    }


def build_draft_lineage_limitations(report: dict[str, object]) -> list[dict[str, str]]:
    draft = dict(report.get("draft", {}))
    if int(draft.get("selections", 0)) == 0:
        evidence = "No draft_selection rows are loaded, so draft lineage cannot be evaluated."
    else:
        evidence = (
            f"{draft.get('resolved_pick_rows', 0)} of {draft.get('selections', 0)} draft selections have "
            "selected-slot resolution rows; this does not reconstruct every prior ownership branch."
        )
    return [
        build_gap(
            "low",
            "Draft-night pick ownership lineage remains deferred.",
            evidence,
            "Keep draft_pick_resolution scoped to selected-player continuity until a separate prior-owner pick lineage table is designed.",
        )
    ]


def build_known_gaps(report: dict[str, object]) -> list[dict[str, str]]:
    counts = dict(report.get("counts", {}))
    event_span_currentness = dict(report.get("event_span_currentness", {}))
    graph_export_span = dict(report.get("graph_export_span", report.get("event_span", {})))
    source_coverage = list(report.get("source_coverage", []))
    source_coverage_report = dict(report.get("source_coverage_report", {}))
    snapshots = dict(report.get("snapshots", {}))
    pick_inventory = dict(report.get("pick_inventory", {}))
    pick_inventory_fixture = dict(report.get("pick_inventory_fixture_gap_report", {}))
    draft = dict(report.get("draft", {}))

    gaps: list[dict[str, str]] = []
    if event_span_currentness and event_span_currentness.get("status") != "verified_quiet_interval":
        gaps.append(
            build_gap(
                "high",
                "Loaded event span is not current to the latest verified Memphis roster event.",
                str(event_span_currentness.get("evidence")),
                "Refresh the source-event load or rerun the dated currentness source review before claiming current coverage.",
            )
        )
    if str(graph_export_span.get("start_date") or "") > "2016-07-01":
        gaps.append(
            build_gap(
                "medium",
                "The graph export span starts after the requested summer 2016 anchor.",
                f"Current graph export start date is {graph_export_span.get('start_date')}.",
                "Confirm whether Memphis had no relevant post-July-1 events before this date or add a source that proves the quiet interval.",
            )
        )
    for gap in source_coverage_report.get("gaps", []):
        if isinstance(gap, dict):
            gaps.append(
                build_gap(
                    str(gap.get("severity", "medium")),
                    str(gap.get("gap")),
                    str(gap.get("evidence")),
                    str(gap.get("next_action")),
                )
            )
    if not any(row.get("source_system") == "nba_stats" for row in source_coverage if isinstance(row, dict)):
        gaps.append(
            build_gap(
                "low",
                "NBA stats reference data is not present in the loaded source records.",
                "The current full-span load can run from Basketball-Reference alone.",
                "Load NBA stats reference data when stronger player IDs or roster endpoint comparisons are needed.",
            )
        )
    if int(snapshots.get("snapshots", 0)) == 0:
        gaps.append(
            build_gap(
                "high",
                "No roster checkpoint snapshots are loaded.",
                "The graph cannot yet validate occupied roster slots over time.",
                "Load or derive roster snapshots before treating the export as roster-truthful.",
            )
        )
    elif int(snapshots.get("derived_from_roster_baseline", 0)) > 0:
        gaps.append(
            build_gap(
                "medium",
                "Roster checkpoint snapshots are approximate.",
                "Some checkpoint rows still use baseline-only roster references instead of date-aware transaction reconstruction.",
                "Rebuild roster checkpoints with the date-aware transaction projection.",
            )
        )
    if int(snapshots.get("pick_rows", 0)) == 0:
        gaps.append(
            build_gap(
                "medium",
                "Future pick inventory snapshots are empty.",
                "No rows exist in foundation.roster_snapshot_pick.",
                "Add a pick-inventory source before relying on pick lanes as complete.",
            )
        )
    elif int(pick_inventory.get("obligations", 0)) == 0:
        gaps.append(
            build_gap(
                "medium",
                "Future pick inventory snapshots are not backed by the obligation ledger.",
                "foundation.roster_snapshot_pick has rows but foundation.pick_inventory_obligation is empty.",
                "Load source-backed pick obligations and rebuild roster_snapshot_pick from that ledger.",
            )
        )
    if int(pick_inventory.get("unknown_owner_rows", 0)) > 0:
        gaps.append(
            build_gap(
                "high",
                "Future pick obligation ledger has UNKNOWN owner rows.",
                f"{pick_inventory.get('unknown_owner_rows')} loaded obligation rows use owner_team_code=UNKNOWN.",
                "Resolve owner semantics from source-backed records before projecting those pick strands as truthful.",
            )
        )
    if int(pick_inventory.get("uncertain_rows", 0)) > 0 or int(pick_inventory.get("documented_only_rows", 0)) > 0:
        gaps.append(
            build_gap(
                "low",
                "Future pick obligation ledger includes caveated documentation rows.",
                (
                    f"{pick_inventory.get('uncertain_rows', 0)} uncertain rows and "
                    f"{pick_inventory.get('documented_only_rows', 0)} documented-only rows are present."
                ),
                "Keep uncertain rows out of live snapshot projection until source semantics are resolved.",
            )
        )
    if int(pick_inventory_fixture.get("unknown_owner_rows", 0)) > 0:
        gaps.append(
            build_gap(
                "high",
                "Future pick obligation fixture has UNKNOWN owner rows.",
                f"{pick_inventory_fixture.get('unknown_owner_rows')} fixture rows use owner_team_code=UNKNOWN.",
                "Update the fixture only when the owner is source-backed; keep unknown rows visible in audit output until then.",
            )
        )
    if int(pick_inventory_fixture.get("non_loadable_rows", 0)) > 0:
        gaps.append(
            build_gap(
                "low",
                "Future pick obligation fixture includes non-loadable fallback documentation rows.",
                f"{pick_inventory_fixture.get('non_loadable_rows')} fixture rows are non-loadable and excluded from projection.",
                "Model conditional branch semantics before making fallback rows projectable graph assets.",
            )
        )
    has_two_way_rows = any(
        isinstance(row, dict) and int(row.get("two_way_rows", 0)) > 0
        for row in list(snapshots.get("contract_status", []))
    )
    if not has_two_way_rows:
        gaps.append(
            build_gap(
                "medium",
                "Two-way roster status is not populated.",
                "Snapshot player rows currently do not prove two-way versus standard slots.",
                "Run the seed_v1 two-way status enrichment after roster snapshots are rebuilt.",
            )
        )
    else:
        gaps.append(
            build_gap(
                "low",
                "Two-way roster status is seed-loaded, not complete historical coverage.",
                "Nonzero two-way snapshot rows prove only the curated high-confidence intervals currently loaded.",
                "Keep using preview-two-way-status/load-two-way-status after roster rebuilds and expand the fixture only with source-backed intervals.",
            )
        )
    if int(draft.get("selections", 0)) > 0 and int(draft.get("unlinked_pick_rows", 0)) > 0:
        gaps.append(
            build_gap(
                "medium",
                "Draft selections are not fully linked back to pick assets.",
                f"{draft.get('unlinked_pick_rows')} draft_selection rows have no pick_id.",
                "Add pick-resolution logic that connects a selected player to the incoming pick asset when the pick is represented in the asset table.",
            )
        )
    elif int(draft.get("selections", 0)) > 0 and int(draft.get("resolved_pick_rows", 0)) < int(draft.get("selections", 0)):
        gaps.append(
            build_gap(
                "low",
                "Draft selections have pick links but not full resolution provenance.",
                f"{draft.get('resolved_pick_rows')} of {draft.get('selections')} draft selections have draft_pick_resolution rows.",
                "Backfill draft_pick_resolution provenance for every linked draft selection.",
            )
        )
    if int(draft.get("selections", 0)) > 0 and int(draft.get("unlinked_source_event_rows", 0)) > 0:
        gaps.append(
            build_gap(
                "medium",
                "Draft selections lack source-event provenance.",
                f"{draft.get('unlinked_source_event_rows')} draft_selection rows have no source_event_id.",
                "Reload draft selections through the checked-in BRef draft loader before treating draft transitions as provenance-complete.",
            )
        )
    if int(draft.get("lottery_results", 0)) == 0:
        gaps.append(
            build_gap(
                "low",
                "Draft lottery results are not loaded.",
                "This is contextual and not required for the base graph, but the table is empty.",
                "Run the seed_v1 draft lottery result preview/load only when contextual lottery annotations are needed.",
            )
        )
    else:
        gaps.append(
            build_gap(
                "low",
                "Draft lottery results are seed-loaded contextual metadata.",
                (
                    f"{draft.get('lottery_results')} rows are loaded; "
                    f"{draft.get('lottery_results_with_owner_original', 0)} carry explicit owner/original-team semantics."
                ),
                "Expand contextual lottery rows only when they are needed for annotations; the base graph export still does not consume them.",
            )
        )
    if int(counts.get("canonical_event", 0)) == 0 or int(counts.get("event_asset_transition", 0)) == 0:
        gaps.append(
            build_gap(
                "high",
                "Canonical events or asset transitions are empty.",
                "The graph export cannot show lineage continuity without these rows.",
                "Run the canonical builder after source/entity loading.",
            )
        )
    for gap in report.get("draft_lineage_limitations", []):
        if isinstance(gap, dict):
            gaps.append(
                build_gap(
                    str(gap.get("severity", "low")),
                    str(gap.get("gap")),
                    str(gap.get("evidence")),
                    str(gap.get("next_action")),
                )
            )
    return gaps


def build_gap(severity: str, gap: str, evidence: str, next_action: str) -> dict[str, str]:
    return {
        "severity": severity,
        "gap": gap,
        "evidence": evidence,
        "next_action": next_action,
    }


def table_exists(connection: psycopg.Connection, table_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass(%s)", (f"foundation.{table_name}",))
        return cursor.fetchone()[0] is not None

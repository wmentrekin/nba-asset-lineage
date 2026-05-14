from __future__ import annotations

import psycopg

from foundation.export import draft_resolution_event_date


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


def audit_foundation_data(database_url: str) -> dict[str, object]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        counts = count_foundation_tables(connection)
        report: dict[str, object] = {
            "status": "ok",
            "counts": counts,
            "event_span": fetch_event_span(connection),
            "graph_export_span": fetch_graph_export_span(connection),
            "source_coverage": fetch_source_coverage(connection),
            "aliases": fetch_alias_metrics(connection),
            "snapshots": fetch_snapshot_metrics(connection),
            "pick_inventory": fetch_pick_inventory_metrics(connection),
            "draft": fetch_draft_metrics(connection),
            "canonical": {
                "events": counts.get("canonical_event", 0),
                "event_members": counts.get("canonical_event_member", 0),
                "transitions": counts.get("event_asset_transition", 0),
            },
        }
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
            "rows_missing_source_event": 0,
            "by_holding_status": [],
            "by_confidence": [],
        }

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select count(*),
                   count(*) filter (where loadable),
                   count(*) filter (where not loadable),
                   count(*) filter (where confidence = 'uncertain'),
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

    return {
        "obligations": int(count_row[0]),
        "loadable_rows": int(count_row[1]),
        "documented_only_rows": int(count_row[2]),
        "uncertain_rows": int(count_row[3]),
        "rows_missing_source_event": int(count_row[4]),
        "by_holding_status": [{"holding_status": str(row[0]), "rows": int(row[1])} for row in holding_rows],
        "by_confidence": [{"confidence": str(row[0]), "rows": int(row[1])} for row in confidence_rows],
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


def build_known_gaps(report: dict[str, object]) -> list[dict[str, str]]:
    counts = dict(report.get("counts", {}))
    graph_export_span = dict(report.get("graph_export_span", report.get("event_span", {})))
    source_coverage = list(report.get("source_coverage", []))
    snapshots = dict(report.get("snapshots", {}))
    pick_inventory = dict(report.get("pick_inventory", {}))
    draft = dict(report.get("draft", {}))

    gaps: list[dict[str, str]] = []
    if str(graph_export_span.get("start_date") or "") > "2016-07-01":
        gaps.append(
            build_gap(
                "medium",
                "The graph export span starts after the requested summer 2016 anchor.",
                f"Current graph export start date is {graph_export_span.get('start_date')}.",
                "Confirm whether Memphis had no relevant post-July-1 events before this date or add a source that proves the quiet interval.",
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

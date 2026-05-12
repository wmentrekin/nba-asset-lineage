from __future__ import annotations

import psycopg

from foundation.models import BaseGraphExport
from foundation.models import AssetTransition, PickAsset, PlayerAsset, TransactionEvent
from foundation.models import RosterSnapshot


def build_empty_base_export() -> BaseGraphExport:
    return BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2016-07-01",
        span_end="2026-06-30",
    )


def build_base_export_from_database(database_url: str) -> BaseGraphExport:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                with latest_baseline as (
                    select distinct on (rbp.player_id)
                           rbp.player_id,
                           rbp.roster_order,
                           rbp.years_experience
                    from foundation.roster_baseline_player rbp
                    where rbp.team_code = 'MEM'
                    order by rbp.player_id, rbp.season desc, rbp.roster_order asc
                )
                select a.asset_id,
                       p.player_id,
                       p.display_name,
                       lb.roster_order,
                       lb.years_experience
                from foundation.asset a
                join foundation.player p on p.player_id = a.player_id
                left join latest_baseline lb on lb.player_id = p.player_id
                where a.asset_kind = 'player'
                order by a.asset_id
                """
            )
            player_rows = cursor.fetchall()

            cursor.execute(
                """
                select a.asset_id,
                       coalesce(pk.original_team, 'unknown') as original_team,
                       pk.draft_year,
                       pk.round_number,
                       pk.protection_text,
                       pk.swap_text
                from foundation.asset a
                join foundation.pick pk on pk.pick_id = a.pick_id
                where a.asset_kind = 'pick'
                order by a.asset_id
                """
            )
            pick_rows = cursor.fetchall()

            cursor.execute(
                """
                select canonical_event_id, event_type, event_date::text, label, sequence_on_date, is_grouped_event
                from foundation.canonical_event
                order by event_date, sequence_on_date, canonical_event_id
                """
            )
            event_rows = cursor.fetchall()

            cursor.execute(
                """
                select transition_id, canonical_event_id, asset_id, transition_type
                from foundation.event_asset_transition
                order by canonical_event_id, transition_id
                """
            )
            transition_rows = cursor.fetchall()

            snapshot_rows: list[tuple[object, ...]] = []
            snapshot_player_rows: list[tuple[object, ...]] = []
            snapshot_pick_rows: list[tuple[object, ...]] = []
            cursor.execute("select to_regclass('foundation.roster_snapshot')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """
                    select snapshot_id, snapshot_date::text, snapshot_kind, season
                    from foundation.roster_snapshot
                    order by snapshot_date, snapshot_kind, snapshot_id
                    """
                )
                snapshot_rows = cursor.fetchall()
                cursor.execute(
                    """
                    select snapshot_id, asset_id, is_two_way
                    from foundation.roster_snapshot_player
                    where asset_id is not null
                    order by snapshot_id, depth_order nulls last, player_id
                    """
                )
                snapshot_player_rows = cursor.fetchall()
                cursor.execute(
                    """
                    select snapshot_id, asset_id
                    from foundation.roster_snapshot_pick
                    where asset_id is not null
                    order by snapshot_id, display_order nulls last, pick_id
                    """
                )
                snapshot_pick_rows = cursor.fetchall()

    export = build_empty_base_export()
    if event_rows:
        export.span_start = str(event_rows[0][2])
        export.span_end = str(event_rows[-1][2])

    export.player_assets = [
        PlayerAsset(
            asset_id=str(row[0]),
            player_id=str(row[1]),
            display_name=str(row[2]),
            baseline_order=int(row[3]) if row[3] is not None else None,
            years_experience=int(row[4]) if row[4] is not None else None,
        )
        for row in player_rows
    ]
    export.pick_assets = [
        PickAsset(
            asset_id=str(row[0]),
            original_team=str(row[1]),
            draft_year=int(row[2]),
            round_number=int(row[3]),
            protections=str(row[4]) if row[4] is not None else None,
            swap_detail=str(row[5]) if row[5] is not None else None,
        )
        for row in pick_rows
    ]
    export.events = [
        TransactionEvent(
            event_id=str(row[0]),
            event_type=str(row[1]),
            event_date=str(row[2]),
            label=str(row[3]),
            sequence=int(row[4]),
            source_group_id=str(row[0]) if bool(row[5]) else None,
        )
        for row in event_rows
    ]
    export.transitions = [
        AssetTransition(
            transition_id=str(row[0]),
            event_id=str(row[1]),
            asset_id=str(row[2]),
            transition_type=str(row[3]),
        )
        for row in transition_rows
    ]
    standard_assets_by_snapshot: dict[str, list[str]] = {}
    two_way_assets_by_snapshot: dict[str, list[str]] = {}
    for snapshot_id, asset_id, is_two_way in snapshot_player_rows:
        target = two_way_assets_by_snapshot if bool(is_two_way) else standard_assets_by_snapshot
        target.setdefault(str(snapshot_id), []).append(str(asset_id))
    pick_assets_by_snapshot: dict[str, list[str]] = {}
    for snapshot_id, asset_id in snapshot_pick_rows:
        pick_assets_by_snapshot.setdefault(str(snapshot_id), []).append(str(asset_id))
    export.roster_snapshots = [
        RosterSnapshot(
            snapshot_id=str(row[0]),
            as_of_date=str(row[1]),
            snapshot_kind=str(row[2]),
            season=str(row[3]),
            roster_asset_ids=standard_assets_by_snapshot.get(str(row[0]), []),
            two_way_asset_ids=two_way_assets_by_snapshot.get(str(row[0]), []),
            future_pick_asset_ids=pick_assets_by_snapshot.get(str(row[0]), []),
        )
        for row in snapshot_rows
    ]
    return export

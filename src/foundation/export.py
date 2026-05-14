from __future__ import annotations

import psycopg
from pydantic import BaseModel

from foundation.models import BaseGraphExport
from foundation.models import AssetTransition, PickAsset, PlayerAsset, TransactionEvent
from foundation.models import FuturePickSnapshot
from foundation.models import RosterSnapshot
from foundation.models import draft_event_date


class DraftResolutionExportRow(BaseModel):
    draft_pick_resolution_id: str
    draft_selection_id: str
    pick_asset_id: str
    player_asset_id: str
    player_name: str
    draft_year: int
    round_number: int
    pick_overall: int
    source_bundle_id: str
    notes: str | None = None
    source_event_id: str | None = None
    canonical_event_id: str | None = None


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

            draft_resolution_rows: list[DraftResolutionExportRow] = []
            cursor.execute("select to_regclass('foundation.draft_pick_resolution')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """
                    select dpr.draft_pick_resolution_id,
                           dpr.draft_selection_id,
                           dpr.pick_asset_id,
                           dpr.player_asset_id,
                           p.display_name,
                           dpr.draft_year,
                           dpr.round_number,
                           dpr.pick_overall,
                           dpr.source_bundle_id,
                           dpr.notes,
                           ds.source_event_id,
                           canonical_draft.canonical_event_id
                    from foundation.draft_pick_resolution dpr
                    join foundation.draft_selection ds on ds.draft_selection_id = dpr.draft_selection_id
                    join foundation.player p on p.player_id = dpr.player_id
                    left join lateral (
                        select cem.canonical_event_id
                        from foundation.canonical_event_member cem
                        join foundation.canonical_event ce
                          on ce.canonical_event_id = cem.canonical_event_id
                        where cem.source_event_id = ds.source_event_id
                          and ce.event_type = 'draft'
                        order by ce.event_date, ce.sequence_on_date, ce.canonical_event_id
                        limit 1
                    ) canonical_draft on true
                    order by dpr.draft_year, dpr.pick_overall, dpr.draft_pick_resolution_id
                    """
                )
                draft_resolution_rows = [
                    DraftResolutionExportRow(
                        draft_pick_resolution_id=str(row[0]),
                        draft_selection_id=str(row[1]),
                        pick_asset_id=str(row[2]),
                        player_asset_id=str(row[3]),
                        player_name=str(row[4]),
                        draft_year=int(row[5]),
                        round_number=int(row[6]),
                        pick_overall=int(row[7]),
                        source_bundle_id=str(row[8]),
                        notes=str(row[9]) if row[9] is not None else None,
                        source_event_id=str(row[10]) if row[10] is not None else None,
                        canonical_event_id=str(row[11]) if row[11] is not None else None,
                    )
                    for row in cursor.fetchall()
                ]

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
                    select snapshot_id,
                           pick_id,
                           asset_id,
                           holding_status,
                           display_order,
                           source_obligation_id,
                           confidence,
                           notes
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
    draft_events, draft_transitions = build_draft_resolution_export_items(draft_resolution_rows)
    export.events = sorted(
        [*export.events, *draft_events],
        key=lambda event: (event.event_date, event.sequence, event.event_id),
    )
    export.transitions = [
        AssetTransition(
            transition_id=str(row[0]),
            event_id=str(row[1]),
            asset_id=str(row[2]),
            transition_type=str(row[3]),
        )
        for row in transition_rows
    ] + draft_transitions
    if export.events:
        export.span_start = min(export.span_start, export.events[0].event_date)
        export.span_end = max(export.span_end, export.events[-1].event_date)
    standard_assets_by_snapshot: dict[str, list[str]] = {}
    two_way_assets_by_snapshot: dict[str, list[str]] = {}
    for snapshot_id, asset_id, is_two_way in snapshot_player_rows:
        target = two_way_assets_by_snapshot if bool(is_two_way) else standard_assets_by_snapshot
        target.setdefault(str(snapshot_id), []).append(str(asset_id))
    pick_assets_by_snapshot: dict[str, list[FuturePickSnapshot]] = {}
    for snapshot_id, pick_id, asset_id, holding_status, display_order, source_obligation_id, confidence, notes in snapshot_pick_rows:
        pick_assets_by_snapshot.setdefault(str(snapshot_id), []).append(
            FuturePickSnapshot(
                asset_id=str(asset_id),
                pick_id=str(pick_id),
                holding_status=str(holding_status),
                display_order=int(display_order) if display_order is not None else None,
                source_obligation_id=str(source_obligation_id) if source_obligation_id is not None else None,
                confidence=str(confidence) if confidence is not None else None,
                notes=str(notes) if notes is not None else None,
            )
        )
    export.roster_snapshots = [
        RosterSnapshot(
            snapshot_id=str(row[0]),
            as_of_date=str(row[1]),
            snapshot_kind=str(row[2]),
            season=str(row[3]),
            roster_asset_ids=standard_assets_by_snapshot.get(str(row[0]), []),
            two_way_asset_ids=two_way_assets_by_snapshot.get(str(row[0]), []),
            future_pick_asset_ids=[pick.asset_id for pick in pick_assets_by_snapshot.get(str(row[0]), [])],
            future_picks=pick_assets_by_snapshot.get(str(row[0]), []),
        )
        for row in snapshot_rows
    ]
    return export


def build_draft_resolution_export_items(
    rows: list[DraftResolutionExportRow],
) -> tuple[list[TransactionEvent], list[AssetTransition]]:
    events: list[TransactionEvent] = []
    transitions: list[AssetTransition] = []
    for row in rows:
        event_id = row.canonical_event_id or build_draft_resolution_event_id(row.draft_selection_id)
        if row.canonical_event_id is None:
            event_date = draft_resolution_event_date(row.draft_year, row.round_number)
            events.append(
                TransactionEvent(
                    event_id=event_id,
                    event_type="draft",
                    event_date=event_date,
                    label=f"Memphis drafts {row.player_name} at No. {row.pick_overall}",
                    sequence=1000 + row.pick_overall,
                    source_group_id=row.source_bundle_id,
                )
            )
        transitions.append(
            AssetTransition(
                transition_id=f"{event_id}:pick-to-player:{row.pick_asset_id}:to:{row.player_asset_id}",
                event_id=event_id,
                asset_id=row.pick_asset_id,
                transition_type="pick_to_player",
                from_state=row.pick_asset_id,
                to_state=row.player_asset_id,
                notes=row.notes,
            )
        )
    return events, transitions


def build_draft_resolution_event_id(draft_selection_id: str) -> str:
    return f"draft-resolution:{draft_selection_id}"


def draft_resolution_event_date(draft_year: int, round_number: int) -> str:
    return draft_event_date(draft_year, round_number)

from __future__ import annotations

import psycopg
from pydantic import BaseModel

from foundation.models import BaseGraphExport, FoundationExportInputs
from foundation.models import AssetTransition, PickAsset, PlayerAsset, TransactionEvent
from foundation.models import FuturePickSnapshot
from foundation.models import ConditionalPickBranchSnapshot, ConditionalPickFamilySnapshot
from foundation.models import DailyRosterState, DailyRosterStatePlayer, DraftLotteryResultExport, DraftPriorOwnerLineage
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


class PickInventoryObligationExportRow(BaseModel):
    obligation_id: str
    effective_date: str
    perspective_team_code: str
    owner_team_code: str
    original_team_code: str
    draft_year: int
    round_number: int
    direction: str
    holding_status: str
    obligation_type: str
    confidence: str
    source_event_id: str | None = None
    canonical_event_id: str | None = None
    protection_text: str | None = None
    swap_text: str | None = None
    condition_text: str | None = None
    notes: str | None = None
    loadable: bool


class DraftLotteryResultDatabaseRow(BaseModel):
    lottery_result_id: str
    draft_year: int
    lottery_date: str | None = None
    team_code: str
    owner_team_code: str | None = None
    original_team_code: str | None = None
    lottery_position: int | None = None
    result_pick_slot: int
    pre_lottery_odds: str | None = None
    notes: str | None = None


def build_empty_base_export() -> BaseGraphExport:
    return BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2016-07-01",
        span_end="2026-06-30",
    )


def _read_base_graph_export_from_database(database_url: str) -> BaseGraphExport:
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
                       pk.pick_id,
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

            daily_state_rows: list[tuple[object, ...]] = []
            daily_state_player_rows: list[tuple[object, ...]] = []
            cursor.execute("select to_regclass('foundation.daily_roster_state')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """
                    select roster_state_id, state_date::text, season
                    from foundation.daily_roster_state
                    where team_code = 'MEM'
                    order by state_date, roster_state_id
                    """
                )
                daily_state_rows = cursor.fetchall()
                cursor.execute(
                    """
                    select rsd.roster_state_id,
                           rsdp.player_id,
                           rsdp.asset_id,
                           rsdp.roster_status,
                           rsdp.roster_order,
                           rsdp.is_two_way,
                           rsdp.is_standard_contract
                    from foundation.daily_roster_state_player rsdp
                    join foundation.daily_roster_state rsd
                      on rsd.roster_state_id = rsdp.roster_state_id
                    where rsd.team_code = 'MEM'
                    order by rsd.state_date, rsd.roster_state_id, rsdp.roster_order nulls last, rsdp.player_id
                    """
                )
                daily_state_player_rows = cursor.fetchall()

            draft_prior_owner_rows: list[tuple[object, ...]] = []
            cursor.execute("select to_regclass('foundation.draft_prior_owner_lineage')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """
                    select draft_selection_id,
                           pick_id,
                           pick_asset_id,
                           player_id,
                           player_asset_id,
                           draft_year,
                           round_number,
                           pick_overall,
                           owner_team_code,
                           original_team_code,
                           source_obligation_id,
                           resolution_kind,
                           confidence,
                           notes
                    from foundation.draft_prior_owner_lineage
                    where team_code = 'MEM'
                    order by draft_year, round_number, pick_overall, draft_selection_id
                    """
                )
                draft_prior_owner_rows = cursor.fetchall()

            pick_inventory_obligation_rows: list[PickInventoryObligationExportRow] = []
            cursor.execute("select to_regclass('foundation.pick_inventory_obligation')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """
                    select obligation_id,
                           effective_date::text,
                           perspective_team_code,
                           owner_team_code,
                           original_team_code,
                           draft_year,
                           round_number,
                           direction,
                           holding_status,
                           obligation_type,
                           confidence,
                           source_event_id,
                           canonical_event_id,
                           protection_text,
                           swap_text,
                           condition_text,
                           notes,
                           loadable
                    from foundation.pick_inventory_obligation
                    where upper(perspective_team_code) = 'MEM'
                    order by effective_date, obligation_id
                    """
                )
                pick_inventory_obligation_rows = [
                    PickInventoryObligationExportRow(
                        obligation_id=str(row[0]),
                        effective_date=str(row[1]),
                        perspective_team_code=str(row[2]),
                        owner_team_code=str(row[3]),
                        original_team_code=str(row[4]),
                        draft_year=int(row[5]),
                        round_number=int(row[6]),
                        direction=str(row[7]),
                        holding_status=str(row[8]),
                        obligation_type=str(row[9]),
                        confidence=str(row[10]),
                        source_event_id=str(row[11]) if row[11] is not None else None,
                        canonical_event_id=str(row[12]) if row[12] is not None else None,
                        protection_text=str(row[13]) if row[13] is not None else None,
                        swap_text=str(row[14]) if row[14] is not None else None,
                        condition_text=str(row[15]) if row[15] is not None else None,
                        notes=str(row[16]) if row[16] is not None else None,
                        loadable=bool(row[17]),
                    )
                    for row in cursor.fetchall()
                ]

            draft_lottery_rows: list[DraftLotteryResultDatabaseRow] = []
            cursor.execute("select to_regclass('foundation.draft_lottery_result')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """
                    select lottery_result_id,
                           draft_year,
                           lottery_date::text,
                           team_code,
                           owner_team_code,
                           original_team_code,
                           lottery_position,
                           result_pick_slot,
                           pre_lottery_odds,
                           notes
                    from foundation.draft_lottery_result
                    where upper(team_code) = 'MEM'
                    order by draft_year, lottery_result_id
                    """
                )
                draft_lottery_rows = [
                    DraftLotteryResultDatabaseRow(
                        lottery_result_id=str(row[0]),
                        draft_year=int(row[1]),
                        lottery_date=str(row[2]) if row[2] is not None else None,
                        team_code=str(row[3]),
                        owner_team_code=str(row[4]) if row[4] is not None else None,
                        original_team_code=str(row[5]) if row[5] is not None else None,
                        lottery_position=int(row[6]) if row[6] is not None else None,
                        result_pick_slot=int(row[7]),
                        pre_lottery_odds=str(row[8]) if row[8] is not None else None,
                        notes=str(row[9]) if row[9] is not None else None,
                    )
                    for row in cursor.fetchall()
                ]

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
            pick_id=str(row[1]),
            original_team=str(row[2]),
            draft_year=int(row[3]),
            round_number=int(row[4]),
            protections=str(row[5]) if row[5] is not None else None,
            swap_detail=str(row[6]) if row[6] is not None else None,
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
            conditional_pick_families=build_conditional_pick_family_snapshots(
                future_picks=pick_assets_by_snapshot.get(str(row[0]), []),
                obligation_rows=pick_inventory_obligation_rows,
            ),
        )
        for row in snapshot_rows
    ]
    player_states_by_day: dict[str, list[DailyRosterStatePlayer]] = {}
    roster_asset_ids_by_day: dict[str, list[str]] = {}
    two_way_asset_ids_by_day: dict[str, list[str]] = {}
    for state_id, player_id, asset_id, roster_status, depth_order, is_two_way, is_standard_contract in daily_state_player_rows:
        if asset_id is None:
            continue
        state_key = str(state_id)
        player_state = DailyRosterStatePlayer(
            asset_id=str(asset_id),
            player_id=str(player_id),
            roster_status=str(roster_status),  # type: ignore[arg-type]
            depth_order=int(depth_order) if depth_order is not None else None,
            is_two_way=bool(is_two_way),
            is_standard_contract=bool(is_standard_contract),
        )
        player_states_by_day.setdefault(state_key, []).append(player_state)
        target = two_way_asset_ids_by_day if bool(is_two_way) else roster_asset_ids_by_day
        target.setdefault(state_key, []).append(str(asset_id))
    export.daily_roster_states = [
        DailyRosterState(
            state_id=str(row[0]),
            as_of_date=str(row[1]),
            season=str(row[2]),
            roster_asset_ids=roster_asset_ids_by_day.get(str(row[0]), []),
            two_way_asset_ids=two_way_asset_ids_by_day.get(str(row[0]), []),
            player_states=player_states_by_day.get(str(row[0]), []),
        )
        for row in daily_state_rows
    ]
    export.draft_prior_owner_lineages = [
        DraftPriorOwnerLineage(
            draft_selection_id=str(row[0]),
            pick_id=str(row[1]),
            pick_asset_id=str(row[2]),
            player_id=str(row[3]),
            player_asset_id=str(row[4]) if row[4] is not None else None,
            draft_year=int(row[5]),
            round_number=int(row[6]),
            pick_overall=int(row[7]),
            owner_team_code=str(row[8]),
            original_team_code=str(row[9]),
            source_obligation_id=str(row[10]) if row[10] is not None else None,
            resolution_kind=str(row[11]),
            confidence=str(row[12]),
            notes=str(row[13]) if row[13] is not None else None,
        )
        for row in draft_prior_owner_rows
    ]
    export.draft_lottery_results = build_draft_lottery_export_rows(
        lottery_rows=draft_lottery_rows,
        pick_assets=export.pick_assets,
        prior_owner_lineages=export.draft_prior_owner_lineages,
    )
    return export


def read_foundation_export_inputs_from_database(database_url: str) -> FoundationExportInputs:
    """Read the database-backed export once and expose it as typed pure-builder inputs.

    This is deliberately read-only.  The projection path supplies the same input
    contract from its in-memory table state instead of opening a connection.
    """

    return FoundationExportInputs.from_base_graph_export(
        _read_base_graph_export_from_database(database_url)
    )


def build_base_export(inputs: FoundationExportInputs) -> BaseGraphExport:
    """Assemble a stable base export without a cursor or database connection."""

    span_start = inputs.span_start
    span_end = inputs.span_end
    if inputs.events:
        ordered_events = sorted(
            inputs.events,
            key=lambda event: (event.event_date, event.sequence, event.event_id),
        )
        span_start = min(span_start, ordered_events[0].event_date)
        span_end = max(span_end, ordered_events[-1].event_date)
    else:
        ordered_events = []
    return BaseGraphExport(
        franchise=inputs.franchise,
        span_start=span_start,
        span_end=span_end,
        events=ordered_events,
        player_assets=inputs.player_assets,
        pick_assets=inputs.pick_assets,
        transitions=inputs.transitions,
        roster_snapshots=inputs.roster_snapshots,
        daily_roster_states=inputs.daily_roster_states,
        draft_prior_owner_lineages=inputs.draft_prior_owner_lineages,
        draft_lottery_results=inputs.draft_lottery_results,
    )


def build_base_export_from_database(database_url: str) -> BaseGraphExport:
    """Compatibility wrapper for callers that currently provide a database URL."""

    inputs = read_foundation_export_inputs_from_database(database_url)
    # Keep the additive draft_lottery_result export surface explicit at this
    # compatibility boundary while the read adapter owns the SQL details.
    draft_lottery_results = inputs.draft_lottery_results
    return build_base_export(inputs.model_copy(update={"draft_lottery_results": draft_lottery_results}))


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


def build_conditional_pick_family_snapshots(
    *,
    future_picks: list[FuturePickSnapshot],
    obligation_rows: list[PickInventoryObligationExportRow],
) -> list[ConditionalPickFamilySnapshot]:
    obligation_by_id = {row.obligation_id: row for row in obligation_rows}
    families: list[ConditionalPickFamilySnapshot] = []
    seen_family_ids: set[str] = set()
    for pick in sorted(future_picks, key=lambda row: (row.display_order or 0, row.pick_id)):
        composite_right = pick.composite_right
        if composite_right is None or composite_right.obligation_role != "primary" or not composite_right.fallback_branches:
            continue
        if composite_right.family_id in seen_family_ids:
            continue
        fallback_branches: list[ConditionalPickBranchSnapshot] = []
        for fallback in composite_right.fallback_branches:
            obligation_id = fallback.obligation_id
            if obligation_id is None:
                continue
            obligation = obligation_by_id.get(obligation_id)
            if obligation is None:
                continue
            pick_ref = build_conditional_pick_ref(
                family_id=composite_right.family_id,
                original_team_code=obligation.original_team_code,
                round_number=obligation.round_number,
            )
            fallback_branches.append(
                ConditionalPickBranchSnapshot(
                    branch_id=build_conditional_branch_id(composite_right.family_id, obligation_id),
                    pick_ref=pick_ref,
                    asset_ref=build_conditional_asset_ref(pick_ref),
                    obligation_id=obligation_id,
                    original_team_code=obligation.original_team_code,
                    round_number=obligation.round_number,
                    trigger_kind=fallback.trigger_kind,
                    protected_pick_start=fallback.protected_pick_start,
                    protected_pick_end=fallback.protected_pick_end,
                    notes=obligation.notes or obligation.condition_text,
                )
            )
        if not fallback_branches:
            continue
        families.append(
            ConditionalPickFamilySnapshot(
                family_id=composite_right.family_id,
                family_kind=composite_right.family_kind,
                selection_rule=composite_right.selection_rule,
                exclusivity_status="unresolved",
                display_original_team_code=composite_right.display_original_team_code,
                primary_pick_id=pick.pick_id,
                primary_asset_id=pick.asset_id,
                primary_source_obligation_id=pick.source_obligation_id,
                fallback_branches=fallback_branches,
            )
        )
        seen_family_ids.add(composite_right.family_id)
    return families


def build_draft_lottery_export_rows(
    *,
    lottery_rows: list[DraftLotteryResultDatabaseRow],
    pick_assets: list[PickAsset],
    prior_owner_lineages: list[DraftPriorOwnerLineage],
) -> list[DraftLotteryResultExport]:
    pick_asset_by_slot: dict[tuple[int, int, str], PickAsset] = {}
    for pick_asset in pick_assets:
        key = (pick_asset.draft_year, pick_asset.round_number, pick_asset.original_team.upper())
        current = pick_asset_by_slot.get(key)
        if current is None or should_prefer_pick_asset(candidate=pick_asset, current=current):
            pick_asset_by_slot[key] = pick_asset

    prior_owner_by_slot = {
        (row.draft_year, row.round_number, row.original_team_code.upper()): row
        for row in prior_owner_lineages
    }

    export_rows: list[DraftLotteryResultExport] = []
    for lottery_row in lottery_rows:
        slot_key = None
        if lottery_row.original_team_code:
            slot_key = (lottery_row.draft_year, 1, lottery_row.original_team_code.upper())
        pick_asset = pick_asset_by_slot.get(slot_key) if slot_key is not None else None
        lineage = prior_owner_by_slot.get(slot_key) if slot_key is not None else None
        export_rows.append(
            DraftLotteryResultExport(
                lottery_result_id=lottery_row.lottery_result_id,
                draft_year=lottery_row.draft_year,
                lottery_date=lottery_row.lottery_date,
                team_code=lottery_row.team_code,
                owner_team_code=lottery_row.owner_team_code,
                original_team_code=lottery_row.original_team_code,
                lottery_position=lottery_row.lottery_position,
                result_pick_slot=lottery_row.result_pick_slot,
                pre_lottery_odds=lottery_row.pre_lottery_odds,
                notes=lottery_row.notes,
                pick_id=pick_asset.pick_id if pick_asset is not None else None,
                pick_asset_id=pick_asset.asset_id if pick_asset is not None else None,
                draft_selection_id=lineage.draft_selection_id if lineage is not None else None,
                draft_selection_player_id=lineage.player_id if lineage is not None else None,
                player_asset_id=lineage.player_asset_id if lineage is not None else None,
            )
        )
    return export_rows


def build_conditional_branch_id(family_id: str, obligation_id: str) -> str:
    return f"conditional-branch:{family_id}:{obligation_id}"


def build_conditional_pick_ref(*, family_id: str, original_team_code: str, round_number: int) -> str:
    return f"pick:conditional:{family_id}:r{round_number}:{original_team_code.lower()}"


def build_conditional_asset_ref(pick_ref: str) -> str:
    return f"asset:conditional-pick:{pick_ref}"


def should_prefer_pick_asset(*, candidate: PickAsset, current: PickAsset) -> bool:
    return current.pick_id.startswith("pick:slot:") and not candidate.pick_id.startswith("pick:slot:")

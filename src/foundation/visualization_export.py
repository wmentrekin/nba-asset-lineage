from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import floor, sqrt

from foundation.models import AssetTransition
from foundation.models import BaseGraphExport
from foundation.models import ConditionalPickBranchSnapshot
from foundation.models import ConditionalPickFamilySnapshot
from foundation.models import DailyRosterState
from foundation.models import DraftPriorOwnerLineage
from foundation.models import FuturePickSnapshot
from foundation.models import PickAsset
from foundation.models import PlayerAsset
from foundation.models import TransactionEvent
from foundation.models import VisualizationAdditiveContext
from foundation.models import VisualizationAsset
from foundation.models import VisualizationConditionalPickBranch
from foundation.models import VisualizationConditionalPickFamily
from foundation.models import VisualizationConnectorKind
from foundation.models import VisualizationDraftLotteryContext
from foundation.models import VisualizationEventConnector
from foundation.models import VisualizationEventNode
from foundation.models import VisualizationEventSummary
from foundation.models import VisualizationExportV1
from foundation.models import VisualizationLane
from foundation.models import VisualizationOccupancyInterval
from foundation.models import VisualizationOccupancyKind
from foundation.models import VisualizationPickMarker
from foundation.models import VisualizationPlayerMarker
from foundation.models import VisualizationSegmentKind
from foundation.models import VisualizationStrandSegment


MAIN_ROSTER_SLOT_COUNT = 15
TWO_WAY_SLOT_COUNT = 3
SUPPORTED_FRANCHISES = frozenset({"MEM", "memphis-grizzlies"})

LEAD_MIN_DAYS = 4
LEAD_MAX_DAYS = 21
LEAD_SCALE = 3
SETTLE_MIN_DAYS = 2
SETTLE_MAX_DAYS = 8
SETTLE_SCALE = 1.75


@dataclass(frozen=True)
class _EventGroup:
    group_key: str
    node_id: str
    canonical_event_id: str
    source_group_id: str | None
    event_type: str
    event_date: str
    sequence: int
    compact_label: str
    detail_label: str | None
    transitions: list[AssetTransition]
    inbound_asset_ids: list[str]
    outbound_asset_ids: list[str]


@dataclass(frozen=True)
class _PlayerDayAssignment:
    state_id: str
    as_of_date: str
    asset_to_lane_id: dict[str, str]
    asset_to_kind: dict[str, VisualizationOccupancyKind]
    overflow_assets: list[str]


@dataclass(frozen=True)
class _PickSnapshotPresence:
    asset_id: str
    lane_id: str
    start_date: date
    end_date: date
    occupancy_kind: VisualizationOccupancyKind
    source_snapshot_id: str | None
    source_obligation_id: str | None


@dataclass(frozen=True)
class _AssetParticipation:
    asset_id: str
    node_id: str
    event_date: date
    event_date_str: str
    event_sequence: int
    role: str
    lead_window_days: int
    settle_window_days: int


@dataclass(frozen=True)
class _WindowSegment:
    asset_id: str
    lane_id: str
    segment_kind: VisualizationSegmentKind
    start_date: date
    end_date: date
    start_node_id: str | None
    end_node_id: str | None


def build_visualization_export(
    base_export: BaseGraphExport,
    *,
    generated_at: str | None = None,
) -> VisualizationExportV1:
    return VisualizationExportBuilder.from_base_export(
        base_export,
        generated_at=generated_at,
    ).build()


class VisualizationExportBuilder:
    def __init__(
        self,
        base_export: BaseGraphExport,
        *,
        generated_at: str | None = None,
    ) -> None:
        self.base_export = base_export
        self.generated_at = generated_at or _default_generated_at()
        self._player_asset_by_id = {
            player.asset_id: player
            for player in self.base_export.player_assets
        }
        self._pick_asset_by_id = {
            pick.asset_id: pick
            for pick in self.base_export.pick_assets
        }
        self._event_by_id = {
            event.event_id: event
            for event in self.base_export.events
        }

    @classmethod
    def from_base_export(
        cls,
        base_export: BaseGraphExport,
        *,
        generated_at: str | None = None,
    ) -> "VisualizationExportBuilder":
        return cls(base_export, generated_at=generated_at)

    def build(self) -> VisualizationExportV1:
        franchise_code = _normalize_franchise_code(self.base_export.franchise)
        if franchise_code not in {"MEM"}:
            raise ValueError("Visualization export builder only supports Memphis for now.")

        assets = self._build_assets()
        asset_label_by_id = {asset.asset_id: asset.display_label for asset in assets}
        player_assignments = self._build_player_day_assignments()
        player_intervals = self._build_player_occupancy_intervals(player_assignments=player_assignments)
        synthetic_player_intervals = self._build_synthetic_player_gap_intervals(
            player_intervals=player_intervals,
        )
        pick_lane_ids, pick_intervals = self._build_pick_occupancy_intervals()
        lanes = self._build_lanes(
            overflow_lane_count=max(
                max((len(item.overflow_assets) for item in player_assignments), default=0),
                max(
                    (
                        int(interval.lane_id.rsplit(":", maxsplit=1)[1])
                        for interval in synthetic_player_intervals
                        if interval.lane_id.startswith("lane:temporary_overflow:")
                    ),
                    default=0,
                ),
            ),
            pick_lane_ids=pick_lane_ids,
        )
        event_groups = self._build_event_groups(asset_label_by_id)
        occupancy_intervals = self._build_occupancy_intervals(
            player_intervals=player_intervals,
            synthetic_player_intervals=synthetic_player_intervals,
            pick_intervals=pick_intervals,
        )
        strand_segments, event_connectors = self._build_strands_and_connectors(
            occupancy_intervals=occupancy_intervals,
            event_groups=event_groups,
        )

        export = VisualizationExportV1(
            franchise="MEM",
            generated_at=self.generated_at,
            source_span_start=self.base_export.span_start,
            source_span_end=self.base_export.span_end,
            render_span_start=self.base_export.span_start,
            render_span_end=self.base_export.span_end,
            lanes=lanes,
            assets=assets,
            occupancy_intervals=occupancy_intervals,
            event_nodes=[
                self._build_event_node(group=group, asset_label_by_id=asset_label_by_id)
                for group in event_groups
            ],
            strand_segments=strand_segments,
            event_connectors=event_connectors,
            additive_context=self._build_additive_context(),
        )
        self._validate_invariants(export)
        return export

    def _build_assets(self) -> list[VisualizationAsset]:
        assets: list[VisualizationAsset] = []

        for player_asset in self.base_export.player_assets:
            assets.append(
                VisualizationAsset(
                    asset_id=player_asset.asset_id,
                    asset_kind="player",
                    marker=VisualizationPlayerMarker(display_name=player_asset.display_name),
                    display_label=player_asset.display_name,
                    foundation_asset_id=player_asset.asset_id,
                    player_id=player_asset.player_id,
                )
            )

        for pick_asset in self.base_export.pick_assets:
            chip_label = _pick_chip_label(pick_asset)
            assets.append(
                VisualizationAsset(
                    asset_id=pick_asset.asset_id,
                    asset_kind="pick",
                    marker=VisualizationPickMarker(chip_label=chip_label),
                    display_label=chip_label,
                    foundation_asset_id=pick_asset.asset_id,
                    pick_id=pick_asset.pick_id,
                )
            )

        return assets

    def _build_player_day_assignments(self) -> list[_PlayerDayAssignment]:
        daily_states = sorted(
            self.base_export.daily_roster_states,
            key=lambda row: (row.as_of_date, row.state_id),
        )
        if not daily_states:
            return []

        first_seen_by_asset = self._build_player_first_seen_dates()
        main_slots: list[str] = []
        two_way_slots: list[str] = []
        overflow_assets: list[str] = []
        overflow_entry_date: dict[str, date] = {}
        assignments: list[_PlayerDayAssignment] = []

        for state in daily_states:
            current_date = _parse_date(state.as_of_date)
            standard_assets: list[str] = []
            two_way_assets: list[str] = []
            for player_state in state.player_states:
                if player_state.asset_id not in self._player_asset_by_id:
                    continue
                if player_state.roster_status == "two_way" or player_state.is_two_way:
                    two_way_assets.append(player_state.asset_id)
                elif player_state.roster_status == "standard":
                    standard_assets.append(player_state.asset_id)

            standard_set = set(standard_assets)
            two_way_set = set(two_way_assets)

            retained_main = [
                asset_id
                for asset_id in main_slots
                if asset_id in standard_set
            ]
            retained_two_way = [
                asset_id
                for asset_id in two_way_slots
                if asset_id in two_way_set
            ]
            retained_overflow = [
                asset_id
                for asset_id in overflow_assets
                if asset_id in standard_set
            ]

            promoted_or_arriving_main = retained_overflow + sorted(
                standard_set - set(retained_main) - set(retained_overflow),
                key=lambda asset_id: self._player_priority_key(
                    asset_id=asset_id,
                    first_seen_by_asset=first_seen_by_asset,
                ),
            )
            next_main = (
                retained_main
                + promoted_or_arriving_main[: max(0, MAIN_ROSTER_SLOT_COUNT - len(retained_main))]
            )[:MAIN_ROSTER_SLOT_COUNT]

            remaining_standard = [
                asset_id
                for asset_id in promoted_or_arriving_main
                if asset_id not in next_main
            ]
            next_overflow = retained_overflow + [
                asset_id
                for asset_id in remaining_standard
                if asset_id not in retained_overflow
            ]
            next_overflow = self._dedupe_preserving_order(next_overflow)
            for asset_id in next_overflow:
                overflow_entry_date.setdefault(asset_id, current_date)
            next_overflow = sorted(
                next_overflow,
                key=lambda asset_id: self._overflow_priority_key(
                    asset_id=asset_id,
                    overflow_entry_date=overflow_entry_date,
                    first_seen_by_asset=first_seen_by_asset,
                ),
            )

            two_way_arrivals = sorted(
                two_way_set - set(retained_two_way),
                key=lambda asset_id: self._player_priority_key(
                    asset_id=asset_id,
                    first_seen_by_asset=first_seen_by_asset,
                ),
            )
            next_two_way = (
                retained_two_way
                + two_way_arrivals[: max(0, TWO_WAY_SLOT_COUNT - len(retained_two_way))]
            )[:TWO_WAY_SLOT_COUNT]
            if len(two_way_set) > TWO_WAY_SLOT_COUNT:
                raise ValueError(
                    f"Two-way occupancy exceeded {TWO_WAY_SLOT_COUNT} slots on {state.as_of_date}."
                )

            asset_to_lane_id: dict[str, str] = {}
            asset_to_kind: dict[str, VisualizationOccupancyKind] = {}

            for slot_index, asset_id in enumerate(next_main, start=1):
                asset_to_lane_id[asset_id] = f"lane:main_roster:{slot_index}"
                asset_to_kind[asset_id] = "main_roster"
            for offset, asset_id in enumerate(next_two_way, start=1):
                slot_index = MAIN_ROSTER_SLOT_COUNT + offset
                asset_to_lane_id[asset_id] = f"lane:two_way:{slot_index}"
                asset_to_kind[asset_id] = "two_way"
            for slot_index, asset_id in enumerate(next_overflow, start=1):
                asset_to_lane_id[asset_id] = f"lane:temporary_overflow:{slot_index}"
                asset_to_kind[asset_id] = "temporary_overflow"

            assignments.append(
                _PlayerDayAssignment(
                    state_id=state.state_id,
                    as_of_date=state.as_of_date,
                    asset_to_lane_id=asset_to_lane_id,
                    asset_to_kind=asset_to_kind,
                    overflow_assets=next_overflow,
                )
            )
            main_slots = next_main
            two_way_slots = next_two_way
            overflow_assets = next_overflow

        return assignments

    def _build_player_first_seen_dates(self) -> dict[str, date]:
        first_seen: dict[str, date] = {}

        for state in self.base_export.daily_roster_states:
            state_date = _parse_date(state.as_of_date)
            for player_state in state.player_states:
                if player_state.asset_id in self._player_asset_by_id:
                    existing = first_seen.get(player_state.asset_id)
                    if existing is None or state_date < existing:
                        first_seen[player_state.asset_id] = state_date

        for transition in self.base_export.transitions:
            event = self._event_by_id.get(transition.event_id)
            if event is None:
                continue
            event_date = _parse_date(event.event_date)
            if transition.transition_type == "acquired" and transition.asset_id in self._player_asset_by_id:
                existing = first_seen.get(transition.asset_id)
                if existing is None or event_date < existing:
                    first_seen[transition.asset_id] = event_date
            if transition.transition_type == "pick_to_player" and transition.to_state in self._player_asset_by_id:
                existing = first_seen.get(transition.to_state)
                if existing is None or event_date < existing:
                    first_seen[transition.to_state] = event_date

        default_start = _parse_date(self.base_export.span_start)
        for asset_id in self._player_asset_by_id:
            first_seen.setdefault(asset_id, default_start)
        return first_seen

    def _build_player_occupancy_intervals(
        self,
        *,
        player_assignments: list[_PlayerDayAssignment],
    ) -> list[VisualizationOccupancyInterval]:
        intervals: list[VisualizationOccupancyInterval] = []
        active_by_asset: dict[str, dict[str, object]] = {}

        for assignment in player_assignments:
            state_date = assignment.as_of_date
            present_assets = set(assignment.asset_to_lane_id)

            for asset_id in list(active_by_asset):
                if asset_id not in present_assets:
                    row = active_by_asset.pop(asset_id)
                    intervals.append(
                        VisualizationOccupancyInterval(
                            interval_id=str(row["interval_id"]),
                            asset_id=asset_id,
                            lane_id=str(row["lane_id"]),
                            start_date=str(row["start_date"]),
                            end_date=str(row["last_date"]),
                            occupancy_kind=str(row["occupancy_kind"]),  # type: ignore[arg-type]
                            source_state_id=str(row["source_state_id"]),
                        )
                    )

            for asset_id, lane_id in assignment.asset_to_lane_id.items():
                occupancy_kind = assignment.asset_to_kind[asset_id]
                row = active_by_asset.get(asset_id)
                if (
                    row is not None
                    and row["lane_id"] == lane_id
                    and row["occupancy_kind"] == occupancy_kind
                    and _parse_date(str(row["last_date"])) + timedelta(days=1) == _parse_date(state_date)
                ):
                    row["last_date"] = state_date
                    continue

                if row is not None:
                    intervals.append(
                        VisualizationOccupancyInterval(
                            interval_id=str(row["interval_id"]),
                            asset_id=asset_id,
                            lane_id=str(row["lane_id"]),
                            start_date=str(row["start_date"]),
                            end_date=str(row["last_date"]),
                            occupancy_kind=str(row["occupancy_kind"]),  # type: ignore[arg-type]
                            source_state_id=str(row["source_state_id"]),
                        )
                    )

                active_by_asset[asset_id] = {
                    "interval_id": f"interval:{asset_id}:{lane_id}:{state_date}",
                    "lane_id": lane_id,
                    "start_date": state_date,
                    "last_date": state_date,
                    "occupancy_kind": occupancy_kind,
                    "source_state_id": assignment.state_id,
                }

        for asset_id, row in active_by_asset.items():
            intervals.append(
                VisualizationOccupancyInterval(
                    interval_id=str(row["interval_id"]),
                    asset_id=asset_id,
                    lane_id=str(row["lane_id"]),
                    start_date=str(row["start_date"]),
                    end_date=str(row["last_date"]),
                    occupancy_kind=str(row["occupancy_kind"]),  # type: ignore[arg-type]
                    source_state_id=str(row["source_state_id"]),
                )
            )

        return sorted(
            intervals,
            key=lambda row: (
                row.start_date,
                row.end_date,
                row.lane_id,
                row.asset_id,
                row.interval_id,
            ),
        )

    def _build_synthetic_player_gap_intervals(
        self,
        *,
        player_intervals: list[VisualizationOccupancyInterval],
    ) -> list[VisualizationOccupancyInterval]:
        intervals_by_asset: dict[str, list[VisualizationOccupancyInterval]] = defaultdict(list)
        for interval in player_intervals:
            if interval.asset_id in self._player_asset_by_id:
                intervals_by_asset[interval.asset_id].append(interval)
        for rows in intervals_by_asset.values():
            rows.sort(key=lambda row: (_parse_date(row.start_date), _parse_date(row.end_date), row.lane_id))

        incoming_dates_by_asset: dict[str, list[date]] = defaultdict(list)
        outgoing_dates_by_asset: dict[str, list[date]] = defaultdict(list)
        for transition in self.base_export.transitions:
            event = self._event_by_id.get(transition.event_id)
            if event is None:
                continue
            event_date = _parse_date(event.event_date)
            if transition.transition_type == "acquired" and transition.asset_id in self._player_asset_by_id:
                incoming_dates_by_asset[transition.asset_id].append(event_date)
            elif transition.transition_type == "departed" and transition.asset_id in self._player_asset_by_id:
                outgoing_dates_by_asset[transition.asset_id].append(event_date)
            elif transition.transition_type == "pick_to_player" and transition.to_state in self._player_asset_by_id:
                incoming_dates_by_asset[str(transition.to_state)].append(event_date)

        unresolved_overflow: list[tuple[str, date, date]] = []
        synthetic_intervals: list[VisualizationOccupancyInterval] = []
        seen_keys: set[tuple[str, str, str, str]] = set()
        created_ranges_by_asset: dict[str, list[tuple[date, date]]] = defaultdict(list)

        for asset_id, incoming_dates in incoming_dates_by_asset.items():
            real_intervals = intervals_by_asset.get(asset_id, [])
            ordered_incoming_dates = sorted(set(incoming_dates))
            ordered_outgoing_dates = sorted(set(outgoing_dates_by_asset.get(asset_id, [])))
            created_ranges = created_ranges_by_asset[asset_id]

            for incoming_date in ordered_incoming_dates:
                if self._interval_exists_on_date(
                    intervals=real_intervals,
                    asset_id=asset_id,
                    target_date=incoming_date,
                ):
                    continue
                if any(start_date <= incoming_date <= end_date for start_date, end_date in created_ranges):
                    continue

                next_real_interval = next(
                    (
                        interval
                        for interval in real_intervals
                        if _parse_date(interval.start_date) >= incoming_date
                    ),
                    None,
                )
                next_outgoing_date = next(
                    (
                        event_date
                        for event_date in ordered_outgoing_dates
                        if event_date >= incoming_date
                    ),
                    None,
                )

                if next_real_interval is not None and _parse_date(next_real_interval.start_date) == incoming_date:
                    continue

                if next_real_interval is not None:
                    synthetic_end = _parse_date(next_real_interval.start_date) - timedelta(days=1)
                    if next_outgoing_date is not None:
                        synthetic_end = min(synthetic_end, next_outgoing_date)
                    if synthetic_end >= incoming_date:
                        key = (
                            asset_id,
                            next_real_interval.lane_id,
                            incoming_date.isoformat(),
                            synthetic_end.isoformat(),
                        )
                        if key not in seen_keys:
                            seen_keys.add(key)
                            created_ranges.append((incoming_date, synthetic_end))
                            synthetic_intervals.append(
                                VisualizationOccupancyInterval(
                                    interval_id=(
                                        f"interval:{asset_id}:{next_real_interval.lane_id}:synthetic-gap:"
                                        f"{incoming_date.isoformat()}"
                                    ),
                                    asset_id=asset_id,
                                    lane_id=next_real_interval.lane_id,
                                    start_date=incoming_date.isoformat(),
                                    end_date=synthetic_end.isoformat(),
                                    occupancy_kind=next_real_interval.occupancy_kind,
                                )
                            )
                    continue

                synthetic_end = next_outgoing_date or incoming_date
                if synthetic_end < incoming_date:
                    continue
                unresolved_overflow.append((asset_id, incoming_date, synthetic_end))

        overflow_lane_by_range = _assign_overflow_lane_slots(
            [(start_date, end_date) for _, start_date, end_date in unresolved_overflow]
        )
        for (asset_id, start_date, end_date), overflow_slot in zip(
            unresolved_overflow,
            overflow_lane_by_range,
            strict=True,
        ):
            lane_id = f"lane:temporary_overflow:{overflow_slot}"
            key = (
                asset_id,
                lane_id,
                start_date.isoformat(),
                end_date.isoformat(),
            )
            if key in seen_keys:
                continue
            if any(
                existing_start <= start_date <= existing_end
                for existing_start, existing_end in created_ranges_by_asset[asset_id]
            ):
                continue
            seen_keys.add(key)
            created_ranges_by_asset[asset_id].append((start_date, end_date))
            synthetic_intervals.append(
                VisualizationOccupancyInterval(
                    interval_id=f"interval:{asset_id}:{lane_id}:synthetic:{start_date.isoformat()}",
                    asset_id=asset_id,
                    lane_id=lane_id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    occupancy_kind="temporary_overflow",
                )
            )

        return sorted(
            synthetic_intervals,
            key=lambda row: (
                row.start_date,
                row.end_date,
                row.lane_id,
                row.asset_id,
                row.interval_id,
            ),
        )

    def _player_priority_key(
        self,
        *,
        asset_id: str,
        first_seen_by_asset: dict[str, date],
    ) -> tuple[date, int, str]:
        player = self._player_asset_by_id[asset_id]
        baseline_order = player.baseline_order if player.baseline_order is not None else 10_000
        return (first_seen_by_asset[asset_id], baseline_order, asset_id)

    def _overflow_priority_key(
        self,
        *,
        asset_id: str,
        overflow_entry_date: dict[str, date],
        first_seen_by_asset: dict[str, date],
    ) -> tuple[date, date, str]:
        return (
            overflow_entry_date.get(asset_id, first_seen_by_asset[asset_id]),
            first_seen_by_asset[asset_id],
            asset_id,
        )

    def _build_pick_occupancy_intervals(
        self,
    ) -> tuple[dict[str, str], list[VisualizationOccupancyInterval]]:
        relevant_pick_asset_ids = self._collect_relevant_pick_asset_ids()
        ordered_pick_asset_ids = sorted(
            relevant_pick_asset_ids,
            key=lambda asset_id: self._pick_lane_sort_key(asset_id),
        )
        pick_lane_ids = {
            asset_id: f"lane:pick:{index}"
            for index, asset_id in enumerate(ordered_pick_asset_ids, start=1)
        }

        intervals: list[VisualizationOccupancyInterval] = []
        snapshot_rows = sorted(
            self.base_export.roster_snapshots,
            key=lambda row: (row.as_of_date, row.snapshot_id),
        )
        snapshot_dates = [_parse_date(row.as_of_date) for row in snapshot_rows]
        interval_keys_seen: set[tuple[str, date, date, str | None, str | None, VisualizationOccupancyKind]] = set()

        for index, snapshot in enumerate(snapshot_rows):
            start_date = _parse_date(snapshot.as_of_date)
            end_date = (
                snapshot_dates[index + 1] - timedelta(days=1)
                if index + 1 < len(snapshot_dates)
                else _parse_date(self.base_export.span_end)
            )
            for future_pick in snapshot.future_picks:
                if future_pick.asset_id not in pick_lane_ids:
                    continue
                occupancy_kind = self._pick_occupancy_kind(
                    future_pick=future_pick,
                    pick_asset=self._pick_asset_by_id.get(future_pick.asset_id),
                )
                key = (
                    future_pick.asset_id,
                    start_date,
                    end_date,
                    snapshot.snapshot_id,
                    future_pick.source_obligation_id,
                    occupancy_kind,
                )
                if key in interval_keys_seen:
                    continue
                interval_keys_seen.add(key)
                intervals.append(
                    VisualizationOccupancyInterval(
                        interval_id=(
                            f"interval:{future_pick.asset_id}:{snapshot.snapshot_id}"
                            f":{start_date.isoformat()}:{end_date.isoformat()}"
                        ),
                        asset_id=future_pick.asset_id,
                        lane_id=pick_lane_ids[future_pick.asset_id],
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                        occupancy_kind=occupancy_kind,
                        source_snapshot_id=snapshot.snapshot_id,
                        source_obligation_id=future_pick.source_obligation_id,
                    )
                )

        for lineage in self.base_export.draft_prior_owner_lineages:
            if lineage.pick_asset_id not in pick_lane_ids:
                continue
            draft_date = _draft_date_for_lineage(lineage)
            if not self._interval_exists_on_date(
                intervals=intervals,
                asset_id=lineage.pick_asset_id,
                target_date=draft_date,
            ):
                intervals.append(
                    VisualizationOccupancyInterval(
                        interval_id=f"interval:{lineage.pick_asset_id}:draft:{lineage.draft_selection_id}",
                        asset_id=lineage.pick_asset_id,
                        lane_id=pick_lane_ids[lineage.pick_asset_id],
                        start_date=draft_date.isoformat(),
                        end_date=draft_date.isoformat(),
                        occupancy_kind="pick_owned",
                        source_obligation_id=lineage.source_obligation_id,
                    )
                )

        for transition in self.base_export.transitions:
            if transition.asset_id not in pick_lane_ids:
                continue
            event = self._event_by_id.get(transition.event_id)
            if event is None:
                continue
            event_date = _parse_date(event.event_date)
            if self._interval_exists_on_date(
                intervals=intervals,
                asset_id=transition.asset_id,
                target_date=event_date,
            ):
                continue
            intervals.append(
                VisualizationOccupancyInterval(
                    interval_id=f"interval:{transition.asset_id}:event:{transition.transition_id}",
                    asset_id=transition.asset_id,
                    lane_id=pick_lane_ids[transition.asset_id],
                    start_date=event_date.isoformat(),
                    end_date=event_date.isoformat(),
                    occupancy_kind="pick_owned",
                )
            )

        return pick_lane_ids, sorted(
            intervals,
            key=lambda row: (
                row.start_date,
                row.end_date,
                row.lane_id,
                row.asset_id,
                row.interval_id,
            ),
        )

    def _collect_relevant_pick_asset_ids(self) -> set[str]:
        relevant: set[str] = set()
        for snapshot in self.base_export.roster_snapshots:
            relevant.update(
                future_pick.asset_id
                for future_pick in snapshot.future_picks
                if future_pick.asset_id in self._pick_asset_by_id
            )
        relevant.update(
            row.pick_asset_id
            for row in self.base_export.draft_prior_owner_lineages
            if row.pick_asset_id in self._pick_asset_by_id
        )
        relevant.update(
            row.pick_asset_id
            for row in self.base_export.draft_lottery_results
            if row.pick_asset_id in self._pick_asset_by_id
        )
        relevant.update(
            transition.asset_id
            for transition in self.base_export.transitions
            if transition.asset_id in self._pick_asset_by_id
        )
        return relevant

    def _pick_lane_sort_key(self, asset_id: str) -> tuple[int, int, str, str]:
        pick = self._pick_asset_by_id[asset_id]
        return (
            pick.draft_year,
            pick.round_number,
            pick.original_team.upper(),
            asset_id,
        )

    def _pick_occupancy_kind(
        self,
        *,
        future_pick: FuturePickSnapshot,
        pick_asset: PickAsset | None,
    ) -> VisualizationOccupancyKind:
        holding_status = future_pick.holding_status.strip().lower()
        composite = future_pick.composite_right or (pick_asset.composite_right if pick_asset is not None else None)

        if composite is not None and composite.fallback_branches:
            if composite.family_kind == "protected_conveyance":
                return "pick_conditional"
            return "pick_swap_right"
        if "swap" in holding_status:
            return "pick_swap_right"
        if "encumber" in holding_status:
            return "pick_encumbered"
        if "owed" in holding_status or "outgoing" in holding_status:
            return "pick_owed_out"
        if "conditional" in holding_status:
            return "pick_conditional"
        return "pick_owned"

    def _build_lanes(
        self,
        *,
        overflow_lane_count: int,
        pick_lane_ids: dict[str, str],
    ) -> list[VisualizationLane]:
        lanes: list[VisualizationLane] = []
        visual_order = 1

        for slot_index in range(1, MAIN_ROSTER_SLOT_COUNT + 1):
            lanes.append(
                VisualizationLane(
                    lane_id=f"lane:main_roster:{slot_index}",
                    band="main_roster",
                    slot_index=slot_index,
                    visual_order=visual_order,
                    is_dynamic=False,
                    label=f"Main {slot_index}",
                )
            )
            visual_order += 1

        for band_offset in range(TWO_WAY_SLOT_COUNT):
            slot_index = MAIN_ROSTER_SLOT_COUNT + band_offset + 1
            lanes.append(
                VisualizationLane(
                    lane_id=f"lane:two_way:{slot_index}",
                    band="two_way",
                    slot_index=slot_index,
                    visual_order=visual_order,
                    is_dynamic=False,
                    label=f"Two-Way {band_offset + 1}",
                )
            )
            visual_order += 1

        for slot_index in range(1, overflow_lane_count + 1):
            lanes.append(
                VisualizationLane(
                    lane_id=f"lane:temporary_overflow:{slot_index}",
                    band="temporary_overflow",
                    slot_index=slot_index,
                    visual_order=visual_order,
                    is_dynamic=True,
                    label=f"Overflow {slot_index}",
                )
            )
            visual_order += 1

        ordered_pick_lane_ids = sorted(
            pick_lane_ids.values(),
            key=lambda lane_id: int(lane_id.rsplit(":", maxsplit=1)[1]),
        )
        for slot_index, lane_id in enumerate(ordered_pick_lane_ids, start=1):
            lanes.append(
                VisualizationLane(
                    lane_id=lane_id,
                    band="pick",
                    slot_index=slot_index,
                    visual_order=visual_order,
                    is_dynamic=True,
                    label=f"Pick {slot_index}",
                )
            )
            visual_order += 1

        return lanes

    def _build_occupancy_intervals(
        self,
        *,
        player_intervals: list[VisualizationOccupancyInterval],
        synthetic_player_intervals: list[VisualizationOccupancyInterval],
        pick_intervals: list[VisualizationOccupancyInterval],
    ) -> list[VisualizationOccupancyInterval]:
        return sorted(
            [
                *player_intervals,
                *synthetic_player_intervals,
                *pick_intervals,
            ],
            key=lambda row: (
                row.start_date,
                row.end_date,
                row.lane_id,
                row.asset_id,
                row.interval_id,
            ),
        )

    def _build_event_groups(
        self,
        asset_label_by_id: dict[str, str],
    ) -> list[_EventGroup]:
        transitions_by_event: dict[str, list[AssetTransition]] = defaultdict(list)
        for transition in self.base_export.transitions:
            transitions_by_event[transition.event_id].append(transition)

        events_by_group_key: dict[tuple[str, str], list[TransactionEvent]] = defaultdict(list)
        for event in self.base_export.events:
            group_id = event.source_group_id or event.event_id
            events_by_group_key[(event.event_date, group_id)].append(event)

        event_groups: list[_EventGroup] = []
        for _, events in sorted(
            events_by_group_key.items(),
            key=lambda item: (
                item[0][0],
                min(event.sequence for event in item[1]),
                item[0][1],
            ),
        ):
            ordered_events = sorted(
                events,
                key=lambda event: (event.sequence, event.event_id),
            )
            representative = ordered_events[0]
            grouped_transitions = [
                transition
                for event in ordered_events
                for transition in transitions_by_event.get(event.event_id, [])
            ]
            inbound_asset_ids = self._group_inbound_asset_ids(grouped_transitions)
            outbound_asset_ids = self._group_outbound_asset_ids(grouped_transitions)
            compact_label = representative.label
            detail_label = None
            if len(ordered_events) > 1:
                compact_label = self._group_compact_label(ordered_events)
                detail_label = representative.label

            event_groups.append(
                _EventGroup(
                    group_key=f"{representative.event_date}:{representative.source_group_id or representative.event_id}",
                    node_id=f"node:{representative.event_id}",
                    canonical_event_id=representative.event_id,
                    source_group_id=representative.source_group_id,
                    event_type=self._resolve_group_event_type(ordered_events),
                    event_date=representative.event_date,
                    sequence=min(event.sequence for event in ordered_events),
                    compact_label=compact_label,
                    detail_label=detail_label,
                    transitions=grouped_transitions,
                    inbound_asset_ids=inbound_asset_ids,
                    outbound_asset_ids=outbound_asset_ids,
                )
            )

        return event_groups

    def _build_event_node(
        self,
        *,
        group: _EventGroup,
        asset_label_by_id: dict[str, str],
    ) -> VisualizationEventNode:
        summary: VisualizationEventSummary | None = None
        if group.event_type == "trade":
            summary = VisualizationEventSummary(
                sent_asset_ids=group.outbound_asset_ids,
                received_asset_ids=group.inbound_asset_ids,
                sent_label=_join_asset_labels(group.outbound_asset_ids, asset_label_by_id),
                received_label=_join_asset_labels(group.inbound_asset_ids, asset_label_by_id),
            )

        return VisualizationEventNode(
            node_id=group.node_id,
            canonical_event_id=group.canonical_event_id,
            source_group_id=group.source_group_id,
            event_type=group.event_type,  # type: ignore[arg-type]
            event_date=group.event_date,
            sequence=group.sequence,
            compact_label=group.compact_label,
            detail_label=group.detail_label,
            summary=summary,
            inbound_asset_ids=group.inbound_asset_ids,
            outbound_asset_ids=group.outbound_asset_ids,
        )

    def _group_compact_label(self, events: Sequence[TransactionEvent]) -> str:
        event_type = self._resolve_group_event_type(events)
        if event_type == "trade":
            return "Grouped trade activity"
        if event_type == "draft":
            return "Draft night activity"
        if event_type == "signing":
            return "Grouped signing activity"
        if event_type == "waiver":
            return "Grouped waiver activity"
        return events[0].label

    def _resolve_group_event_type(self, events: Sequence[TransactionEvent]) -> str:
        event_types = {event.event_type for event in events}
        if len(event_types) == 1:
            return events[0].event_type
        if "trade" in event_types:
            return "trade"
        return events[0].event_type

    def _group_inbound_asset_ids(self, transitions: Sequence[AssetTransition]) -> list[str]:
        inbound: list[str] = []
        for transition in transitions:
            if transition.transition_type == "acquired":
                inbound.append(transition.asset_id)
            elif transition.transition_type == "pick_to_player" and transition.to_state is not None:
                inbound.append(transition.to_state)
        return _unique_preserving_order(inbound)

    def _group_outbound_asset_ids(self, transitions: Sequence[AssetTransition]) -> list[str]:
        outbound: list[str] = []
        for transition in transitions:
            if transition.transition_type == "departed":
                outbound.append(transition.asset_id)
            elif transition.transition_type == "pick_to_player":
                outbound.append(transition.asset_id)
        return _unique_preserving_order(outbound)

    def _build_strands_and_connectors(
        self,
        *,
        occupancy_intervals: list[VisualizationOccupancyInterval],
        event_groups: list[_EventGroup],
    ) -> tuple[list[VisualizationStrandSegment], list[VisualizationEventConnector]]:
        intervals_by_asset: dict[str, list[VisualizationOccupancyInterval]] = defaultdict(list)
        for interval in occupancy_intervals:
            intervals_by_asset[interval.asset_id].append(interval)
        for rows in intervals_by_asset.values():
            rows.sort(key=lambda row: (_parse_date(row.start_date), _parse_date(row.end_date), row.lane_id))

        participations = self._build_asset_participations(
            intervals_by_asset=intervals_by_asset,
            event_groups=event_groups,
        )
        segments = self._build_segments(
            intervals_by_asset=intervals_by_asset,
            participations=participations,
        )
        connectors = self._build_connectors(
            intervals_by_asset=intervals_by_asset,
            participations=participations,
            event_groups=event_groups,
        )
        return segments, connectors

    def _build_asset_participations(
        self,
        *,
        intervals_by_asset: dict[str, list[VisualizationOccupancyInterval]],
        event_groups: list[_EventGroup],
    ) -> dict[str, list[_AssetParticipation]]:
        tentative: dict[str, list[dict[str, object]]] = defaultdict(list)
        event_sequence_by_node = {group.node_id: group.sequence for group in event_groups}
        group_by_node = {group.node_id: group for group in event_groups}
        event_to_node = {
            event_id: group.node_id
            for group in event_groups
            for event_id in {group.canonical_event_id, *(transition.event_id for transition in group.transitions)}
        }

        for group in event_groups:
            event_date = _parse_date(group.event_date)
            converted_player_asset_ids = {
                str(transition.to_state)
                for transition in group.transitions
                if transition.transition_type == "pick_to_player" and transition.to_state is not None
            }
            for transition in group.transitions:
                node_id = event_to_node[transition.event_id]
                if transition.transition_type == "acquired":
                    if transition.asset_id in converted_player_asset_ids:
                        continue
                    tentative[transition.asset_id].append(
                        {
                            "node_id": node_id,
                            "event_date": event_date,
                            "event_date_str": group.event_date,
                            "event_sequence": event_sequence_by_node[node_id],
                            "role": "incoming",
                        }
                    )
                elif transition.transition_type == "departed":
                    role = "termination" if group.event_type == "waiver" else "outgoing"
                    tentative[transition.asset_id].append(
                        {
                            "node_id": node_id,
                            "event_date": event_date,
                            "event_date_str": group.event_date,
                            "event_sequence": event_sequence_by_node[node_id],
                            "role": role,
                        }
                    )
                elif transition.transition_type == "pick_to_player":
                    tentative[transition.asset_id].append(
                        {
                            "node_id": node_id,
                            "event_date": event_date,
                            "event_date_str": group.event_date,
                            "event_sequence": event_sequence_by_node[node_id],
                            "role": "conversion_out",
                        }
                    )
                    if transition.to_state is not None:
                        tentative[transition.to_state].append(
                            {
                                "node_id": node_id,
                                "event_date": event_date,
                                "event_date_str": group.event_date,
                                "event_sequence": event_sequence_by_node[node_id],
                                "role": "conversion_in",
                            }
                        )

        aligned_by_asset: dict[str, list[_AssetParticipation]] = {}
        for asset_id, rows in tentative.items():
            rows.sort(
                key=lambda row: (
                    row["event_date"],
                    int(row["event_sequence"]),
                    str(row["node_id"]),
                    str(row["role"]),
                )
            )
            asset_start = self._asset_first_date(intervals_by_asset.get(asset_id, []), rows)
            asset_end = self._asset_last_date(intervals_by_asset.get(asset_id, []), rows)

            computed_rows: list[dict[str, object]] = []
            for index, row in enumerate(rows):
                current_date = row["event_date"]
                prev_date = rows[index - 1]["event_date"] if index > 0 else asset_start
                next_date = rows[index + 1]["event_date"] if index + 1 < len(rows) else asset_end
                prev_gap_days = max(0, (current_date - prev_date).days)
                next_gap_days = max(0, (next_date - current_date).days)
                computed_rows.append(
                    {
                        **row,
                        "lead_window_days": _clamp_window(
                            floor(sqrt(prev_gap_days) * LEAD_SCALE),
                            LEAD_MIN_DAYS,
                            LEAD_MAX_DAYS,
                        ),
                        "settle_window_days": _clamp_window(
                            floor(sqrt(next_gap_days) * SETTLE_SCALE),
                            SETTLE_MIN_DAYS,
                            SETTLE_MAX_DAYS,
                        ),
                    }
                )

            aligned_by_node: dict[str, dict[str, int]] = defaultdict(lambda: {"lead": 0, "settle": 0})
            for row in computed_rows:
                role = str(row["role"])
                if role in {"outgoing", "termination", "conversion_out"}:
                    aligned_by_node[str(row["node_id"])]["lead"] = max(
                        aligned_by_node[str(row["node_id"])]["lead"],
                        int(row["lead_window_days"]),
                    )
                if role in {"incoming", "conversion_in"}:
                    aligned_by_node[str(row["node_id"])]["settle"] = max(
                        aligned_by_node[str(row["node_id"])]["settle"],
                        int(row["settle_window_days"]),
                    )

            aligned_rows: list[_AssetParticipation] = []
            for row in computed_rows:
                node_alignment = aligned_by_node[str(row["node_id"])]
                role = str(row["role"])
                lead_window = int(row["lead_window_days"])
                settle_window = int(row["settle_window_days"])
                if role in {"outgoing", "termination", "conversion_out"}:
                    lead_window = node_alignment["lead"]
                if role in {"incoming", "conversion_in"}:
                    settle_window = node_alignment["settle"]
                aligned_rows.append(
                    _AssetParticipation(
                        asset_id=asset_id,
                        node_id=str(row["node_id"]),
                        event_date=row["event_date"],
                        event_date_str=str(row["event_date_str"]),
                        event_sequence=int(row["event_sequence"]),
                        role=role,
                        lead_window_days=lead_window,
                        settle_window_days=settle_window,
                    )
                )
            aligned_rows.sort(
                key=lambda row: (
                    row.event_date,
                    row.event_sequence,
                    row.node_id,
                    row.role,
                )
            )
            aligned_by_asset[asset_id] = aligned_rows

        return aligned_by_asset

    def _build_segments(
        self,
        *,
        intervals_by_asset: dict[str, list[VisualizationOccupancyInterval]],
        participations: dict[str, list[_AssetParticipation]],
    ) -> list[VisualizationStrandSegment]:
        segments: list[VisualizationStrandSegment] = []
        for asset_id, intervals in intervals_by_asset.items():
            windows_by_interval_index: dict[int, list[_WindowSegment]] = defaultdict(list)
            for participation in participations.get(asset_id, []):
                if participation.role in {"outgoing", "termination", "conversion_out"}:
                    interval_index, interval = self._find_interval_before_or_on(
                        intervals=intervals,
                        target_date=participation.event_date,
                    )
                    if interval is None:
                        continue
                    start_date = max(
                        _parse_date(interval.start_date),
                        participation.event_date - timedelta(days=participation.lead_window_days),
                    )
                    kind: VisualizationSegmentKind = "event_lead_in"
                    if participation.role == "termination":
                        kind = "termination"
                    elif participation.role == "conversion_out":
                        kind = "draft_conversion"
                    windows_by_interval_index[interval_index].append(
                        _WindowSegment(
                            asset_id=asset_id,
                            lane_id=interval.lane_id,
                            segment_kind=kind,
                            start_date=start_date,
                            end_date=participation.event_date,
                            start_node_id=None,
                            end_node_id=participation.node_id,
                        )
                    )
                if participation.role in {"incoming", "conversion_in"}:
                    interval_index, interval = self._find_interval_on_or_after(
                        intervals=intervals,
                        target_date=participation.event_date,
                    )
                    if interval is None:
                        continue
                    end_date = min(
                        _parse_date(interval.end_date),
                        participation.event_date + timedelta(days=participation.settle_window_days),
                    )
                    kind = "event_settle_in" if participation.role == "incoming" else "draft_conversion"
                    windows_by_interval_index[interval_index].append(
                        _WindowSegment(
                            asset_id=asset_id,
                            lane_id=interval.lane_id,
                            segment_kind=kind,
                            start_date=participation.event_date,
                            end_date=end_date,
                            start_node_id=participation.node_id,
                            end_node_id=None,
                        )
                    )

            for interval_index, interval in enumerate(intervals):
                start_date = _parse_date(interval.start_date)
                end_date = _parse_date(interval.end_date)
                windows = sorted(
                    windows_by_interval_index.get(interval_index, []),
                    key=lambda row: (row.start_date, row.end_date, row.segment_kind),
                )
                clip_ranges = [
                    (
                        max(start_date, window.start_date),
                        min(end_date, window.end_date),
                    )
                    for window in windows
                    if max(start_date, window.start_date) <= min(end_date, window.end_date)
                ]
                merged_clip_ranges = _merge_date_ranges(clip_ranges)
                current_start = start_date
                resident_index = 1
                for clip_start, clip_end in merged_clip_ranges:
                    resident_end = clip_start - timedelta(days=1)
                    if current_start <= resident_end:
                        segments.append(
                            VisualizationStrandSegment(
                                segment_id=(
                                    f"segment:{asset_id}:{interval.lane_id}:resident:{resident_index}"
                                    f":{current_start.isoformat()}:{resident_end.isoformat()}"
                                ),
                                asset_id=asset_id,
                                lane_id=interval.lane_id,
                                segment_kind="resident",
                                start_date=current_start.isoformat(),
                                end_date=resident_end.isoformat(),
                            )
                        )
                        resident_index += 1
                    current_start = clip_end + timedelta(days=1)
                if current_start <= end_date:
                    segments.append(
                        VisualizationStrandSegment(
                            segment_id=(
                                f"segment:{asset_id}:{interval.lane_id}:resident:{resident_index}"
                                f":{current_start.isoformat()}:{end_date.isoformat()}"
                            ),
                            asset_id=asset_id,
                            lane_id=interval.lane_id,
                            segment_kind="resident",
                            start_date=current_start.isoformat(),
                            end_date=end_date.isoformat(),
                        )
                    )

                for window_index, window in enumerate(windows, start=1):
                    segments.append(
                        VisualizationStrandSegment(
                            segment_id=(
                                f"segment:{asset_id}:{interval.lane_id}:{window.segment_kind}:{window_index}"
                                f":{window.start_date.isoformat()}:{window.end_date.isoformat()}"
                            ),
                            asset_id=asset_id,
                            lane_id=window.lane_id,
                            segment_kind=window.segment_kind,
                            start_date=window.start_date.isoformat(),
                            end_date=window.end_date.isoformat(),
                            start_node_id=window.start_node_id,
                            end_node_id=window.end_node_id,
                        )
                    )

        return sorted(
            segments,
            key=lambda row: (
                row.start_date,
                row.end_date,
                row.lane_id,
                row.asset_id,
                row.segment_id,
            ),
        )

    def _build_connectors(
        self,
        *,
        intervals_by_asset: dict[str, list[VisualizationOccupancyInterval]],
        participations: dict[str, list[_AssetParticipation]],
        event_groups: list[_EventGroup],
    ) -> list[VisualizationEventConnector]:
        connectors: list[VisualizationEventConnector] = []
        node_ids_by_date: dict[str, list[str]] = defaultdict(list)
        for group in event_groups:
            node_ids_by_date[group.event_date].append(group.node_id)

        for asset_id, rows in participations.items():
            intervals = intervals_by_asset.get(asset_id, [])
            for participation in rows:
                connector_kind: VisualizationConnectorKind
                from_lane_id: str | None = None
                to_lane_id: str | None = None

                if participation.role in {"outgoing", "termination", "conversion_out"}:
                    _, interval = self._find_interval_before_or_on(
                        intervals=intervals,
                        target_date=participation.event_date,
                    )
                    from_lane_id = interval.lane_id if interval is not None else None
                if participation.role in {"incoming", "conversion_in"}:
                    _, interval = self._find_interval_on_or_after(
                        intervals=intervals,
                        target_date=participation.event_date,
                    )
                    to_lane_id = interval.lane_id if interval is not None else None

                if participation.role == "outgoing":
                    connector_kind = "outgoing"
                elif participation.role == "incoming":
                    connector_kind = "incoming"
                elif participation.role == "termination":
                    connector_kind = "termination"
                else:
                    connector_kind = "conversion"

                connectors.append(
                    VisualizationEventConnector(
                        connector_id=(
                            f"connector:{participation.node_id}:{asset_id}:{participation.role}"
                        ),
                        node_id=participation.node_id,
                        asset_id=asset_id,
                        connector_kind=connector_kind,
                        from_lane_id=from_lane_id,
                        to_lane_id=to_lane_id,
                        lead_window_days=participation.lead_window_days,
                        settle_window_days=participation.settle_window_days,
                    )
                )

        for asset_id, intervals in intervals_by_asset.items():
            if asset_id not in self._player_asset_by_id:
                continue
            for previous, current in zip(intervals, intervals[1:], strict=False):
                previous_end = _parse_date(previous.end_date)
                current_start = _parse_date(current.start_date)
                if previous.lane_id == current.lane_id:
                    continue
                if current_start - previous_end > timedelta(days=1):
                    continue
                connector_date = current.start_date if node_ids_by_date.get(current.start_date) else previous.end_date
                candidate_nodes = node_ids_by_date.get(connector_date, [])
                if not candidate_nodes:
                    continue
                connectors.append(
                    VisualizationEventConnector(
                        connector_id=f"connector:{candidate_nodes[0]}:{asset_id}:lane-shift:{current.start_date}",
                        node_id=candidate_nodes[0],
                        asset_id=asset_id,
                        connector_kind="lane_shift",
                        from_lane_id=previous.lane_id,
                        to_lane_id=current.lane_id,
                        lead_window_days=0,
                        settle_window_days=0,
                    )
                )

        unique: dict[str, VisualizationEventConnector] = {}
        for connector in connectors:
            unique[connector.connector_id] = connector
        return sorted(
            unique.values(),
            key=lambda row: (
                row.node_id,
                row.asset_id,
                row.connector_kind,
                row.connector_id,
            ),
        )

    def _build_additive_context(self) -> VisualizationAdditiveContext:
        conditional_family_by_id: dict[str, VisualizationConditionalPickFamily] = {}

        for snapshot in sorted(self.base_export.roster_snapshots, key=lambda row: (row.as_of_date, row.snapshot_id)):
            for family in snapshot.conditional_pick_families:
                conditional_family_by_id[family.family_id] = self._build_conditional_pick_family(family)

        lottery_results = [
            VisualizationDraftLotteryContext(
                lottery_result_id=row.lottery_result_id,
                draft_year=row.draft_year,
                lottery_date=row.lottery_date,
                original_team_code=row.original_team_code,
                owner_team_code=row.owner_team_code,
                result_pick_slot=row.result_pick_slot,
                pick_id=row.pick_id,
                pick_asset_id=row.pick_asset_id,
                draft_selection_id=row.draft_selection_id,
            )
            for row in self.base_export.draft_lottery_results
        ]

        return VisualizationAdditiveContext(
            conditional_pick_families=[
                conditional_family_by_id[family_id]
                for family_id in sorted(conditional_family_by_id)
            ],
            draft_lottery_results=lottery_results,
        )

    def _build_conditional_pick_family(
        self,
        family: ConditionalPickFamilySnapshot,
    ) -> VisualizationConditionalPickFamily:
        return VisualizationConditionalPickFamily(
            family_id=family.family_id,
            family_kind=family.family_kind,
            selection_rule=family.selection_rule,
            exclusivity_status=family.exclusivity_status,
            primary_pick_id=family.primary_pick_id,
            primary_asset_id=family.primary_asset_id,
            fallback_branches=[
                self._build_conditional_pick_branch(branch)
                for branch in family.fallback_branches
            ],
        )

    def _build_conditional_pick_branch(
        self,
        branch: ConditionalPickBranchSnapshot,
    ) -> VisualizationConditionalPickBranch:
        return VisualizationConditionalPickBranch(
            branch_id=branch.branch_id,
            original_team_code=branch.original_team_code,
            round_number=branch.round_number,
            trigger_kind=branch.trigger_kind,
            notes=branch.notes,
        )

    def _find_interval_before_or_on(
        self,
        *,
        intervals: Sequence[VisualizationOccupancyInterval],
        target_date: date,
    ) -> tuple[int, VisualizationOccupancyInterval | None]:
        best_index = -1
        best_interval: VisualizationOccupancyInterval | None = None
        for index, interval in enumerate(intervals):
            start_date = _parse_date(interval.start_date)
            end_date = _parse_date(interval.end_date)
            if start_date <= target_date <= end_date:
                return index, interval
            if end_date <= target_date:
                best_index = index
                best_interval = interval
        return best_index, best_interval

    def _find_interval_on_or_after(
        self,
        *,
        intervals: Sequence[VisualizationOccupancyInterval],
        target_date: date,
    ) -> tuple[int, VisualizationOccupancyInterval | None]:
        best_index = -1
        best_interval: VisualizationOccupancyInterval | None = None
        for index, interval in enumerate(intervals):
            start_date = _parse_date(interval.start_date)
            end_date = _parse_date(interval.end_date)
            if start_date <= target_date <= end_date:
                return index, interval
            if start_date >= target_date:
                return index, interval
            best_index = index
            best_interval = interval
        return best_index, best_interval

    def _asset_first_date(
        self,
        intervals: Sequence[VisualizationOccupancyInterval],
        rows: Sequence[dict[str, object]],
    ) -> date:
        if intervals:
            return min(_parse_date(interval.start_date) for interval in intervals)
        if rows:
            return min(row["event_date"] for row in rows)  # type: ignore[return-value]
        return _parse_date(self.base_export.span_start)

    def _asset_last_date(
        self,
        intervals: Sequence[VisualizationOccupancyInterval],
        rows: Sequence[dict[str, object]],
    ) -> date:
        if intervals:
            return max(_parse_date(interval.end_date) for interval in intervals)
        if rows:
            return max(row["event_date"] for row in rows)  # type: ignore[return-value]
        return _parse_date(self.base_export.span_end)

    def _interval_exists_on_date(
        self,
        *,
        intervals: Sequence[VisualizationOccupancyInterval],
        asset_id: str,
        target_date: date,
    ) -> bool:
        for interval in intervals:
            if interval.asset_id != asset_id:
                continue
            if _parse_date(interval.start_date) <= target_date <= _parse_date(interval.end_date):
                return True
        return False

    def _validate_invariants(self, export: VisualizationExportV1) -> None:
        lane_ids = {lane.lane_id for lane in export.lanes}
        asset_ids = {asset.asset_id for asset in export.assets}
        node_ids = {node.node_id for node in export.event_nodes}

        by_date_main: dict[str, set[str]] = defaultdict(set)
        by_date_two_way: dict[str, set[str]] = defaultdict(set)
        by_asset_date: dict[tuple[str, str], set[str]] = defaultdict(set)

        for interval in export.occupancy_intervals:
            if interval.lane_id not in lane_ids:
                raise ValueError(f"Unknown lane_id in occupancy interval: {interval.lane_id}")
            if interval.asset_id not in asset_ids:
                raise ValueError(f"Unknown asset_id in occupancy interval: {interval.asset_id}")
            if interval.asset_id in self._player_asset_by_id:
                for day_string in _date_range_strings(interval.start_date, interval.end_date):
                    by_asset_date[(interval.asset_id, day_string)].add(interval.lane_id)
                    if interval.occupancy_kind == "main_roster":
                        by_date_main[day_string].add(interval.lane_id)
                    elif interval.occupancy_kind == "two_way":
                        by_date_two_way[day_string].add(interval.lane_id)

        for (asset_id, day_string), lanes in by_asset_date.items():
            if len(lanes) > 1:
                raise ValueError(
                    f"Player asset {asset_id} occupies multiple lanes on {day_string}: {sorted(lanes)}"
                )

        for day_string, lanes in by_date_main.items():
            if len(lanes) > MAIN_ROSTER_SLOT_COUNT:
                raise ValueError(f"Main-roster lane occupancy exceeds {MAIN_ROSTER_SLOT_COUNT} on {day_string}.")
        for day_string, lanes in by_date_two_way.items():
            if len(lanes) > TWO_WAY_SLOT_COUNT:
                raise ValueError(f"Two-way lane occupancy exceeds {TWO_WAY_SLOT_COUNT} on {day_string}.")

        conversion_out_by_node: dict[str, int] = defaultdict(int)
        conversion_in_by_node: dict[str, int] = defaultdict(int)
        for connector in export.event_connectors:
            if connector.node_id not in node_ids:
                raise ValueError(f"Unknown node_id in connector: {connector.node_id}")
            if connector.asset_id not in asset_ids:
                raise ValueError(f"Unknown asset_id in connector: {connector.asset_id}")
            if connector.connector_kind == "conversion":
                if connector.from_lane_id is not None:
                    conversion_out_by_node[connector.node_id] += 1
                if connector.to_lane_id is not None:
                    conversion_in_by_node[connector.node_id] += 1

        for segment in export.strand_segments:
            if segment.lane_id not in lane_ids:
                raise ValueError(f"Unknown lane_id in strand segment: {segment.lane_id}")
            if segment.asset_id not in asset_ids:
                raise ValueError(f"Unknown asset_id in strand segment: {segment.asset_id}")
            if segment.start_node_id is not None and segment.start_node_id not in node_ids:
                raise ValueError(f"Unknown start_node_id in strand segment: {segment.start_node_id}")
            if segment.end_node_id is not None and segment.end_node_id not in node_ids:
                raise ValueError(f"Unknown end_node_id in strand segment: {segment.end_node_id}")
            if segment.segment_kind == "termination" and segment.end_node_id is None:
                raise ValueError("Termination segments must end at a node.")

        draft_node_ids = {
            node.node_id
            for node in export.event_nodes
            if node.event_type == "draft"
        }
        for node_id in draft_node_ids:
            if conversion_out_by_node[node_id] != conversion_in_by_node[node_id]:
                raise ValueError(
                    f"Draft node {node_id} has mismatched conversion surfaces: "
                    f"{conversion_out_by_node[node_id]} outgoing vs {conversion_in_by_node[node_id]} incoming."
                )

    def _dedupe_preserving_order(self, values: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered


def _normalize_franchise_code(value: str) -> str:
    normalized = value.strip()
    if normalized not in SUPPORTED_FRANCHISES:
        raise ValueError(f"Visualization export builder only supports Memphis for now, got {value!r}.")
    return "MEM"


def _pick_chip_label(pick_asset: PickAsset) -> str:
    return f"{pick_asset.draft_year} R{pick_asset.round_number} {pick_asset.original_team.upper()}"


def _join_asset_labels(asset_ids: Iterable[str], asset_label_by_id: dict[str, str]) -> str | None:
    labels = [
        asset_label_by_id[asset_id]
        for asset_id in asset_ids
        if asset_id in asset_label_by_id
    ]
    if not labels:
        return None
    return ", ".join(labels)


def _unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _default_generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _draft_date_for_lineage(lineage: DraftPriorOwnerLineage) -> date:
    from foundation.models import draft_event_date

    return _parse_date(draft_event_date(lineage.draft_year, lineage.round_number))


def _clamp_window(raw_value: int, min_days: int, max_days: int) -> int:
    if raw_value <= 0:
        return min_days
    return max(min_days, min(max_days, raw_value))


def _merge_date_ranges(ranges: Sequence[tuple[date, date]]) -> list[tuple[date, date]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda row: (row[0], row[1]))
    merged: list[tuple[date, date]] = [ordered[0]]
    for start_date, end_date in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start_date <= previous_end + timedelta(days=1):
            merged[-1] = (previous_start, max(previous_end, end_date))
            continue
        merged.append((start_date, end_date))
    return merged


def _date_range_strings(start_date: str, end_date: str) -> list[str]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _assign_overflow_lane_slots(
    ranges: Sequence[tuple[date, date]],
) -> list[int]:
    active_until_by_slot: list[date] = []
    assigned_slots: list[int] = []
    for start_date, end_date in ranges:
        assigned_slot: int | None = None
        for index, active_until in enumerate(active_until_by_slot):
            if active_until < start_date:
                assigned_slot = index + 1
                active_until_by_slot[index] = end_date
                break
        if assigned_slot is None:
            active_until_by_slot.append(end_date)
            assigned_slot = len(active_until_by_slot)
        assigned_slots.append(assigned_slot)
    return assigned_slots

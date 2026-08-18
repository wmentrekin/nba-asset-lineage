from __future__ import annotations
from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field, model_validator


AssetKind = Literal["player", "pick"]
EventType = Literal[
    "trade",
    "draft",
    "waiver",
    "signing",
]
TransitionType = Literal["continuity", "pick_to_player", "acquired", "departed"]
ConditionalPickFamilyStatus = Literal["unresolved", "primary_realized", "fallback_realized"]


DRAFT_DATE_BY_YEAR_ROUND = {
    (2016, 1): "2016-06-23",
    (2016, 2): "2016-06-23",
    (2017, 1): "2017-06-22",
    (2017, 2): "2017-06-22",
    (2018, 1): "2018-06-21",
    (2018, 2): "2018-06-21",
    (2019, 1): "2019-06-20",
    (2019, 2): "2019-06-20",
    (2020, 1): "2020-11-18",
    (2020, 2): "2020-11-18",
    (2021, 1): "2021-07-29",
    (2021, 2): "2021-07-29",
    (2022, 1): "2022-06-23",
    (2022, 2): "2022-06-23",
    (2023, 1): "2023-06-22",
    (2023, 2): "2023-06-22",
    (2024, 1): "2024-06-26",
    (2024, 2): "2024-06-27",
    (2025, 1): "2025-06-25",
    (2025, 2): "2025-06-26",
    # The 2026 draft returned to the two-night Tuesday/Wednesday schedule.
    (2026, 1): "2026-06-23",
    (2026, 2): "2026-06-24",
}


def draft_event_date(draft_year: int, round_number: int) -> str:
    event_date = DRAFT_DATE_BY_YEAR_ROUND.get((draft_year, round_number))
    if event_date is None:
        raise ValueError(f"Missing draft event date for draft_year={draft_year}, round_number={round_number}")
    return event_date


CompositeRightKind = Literal[
    "protected_conveyance",
    "most_favorable_set",
    "realized_swap_path",
    "protected_swap_right",
    "tiered_swap_ladder",
]
CompositeRightRole = Literal["primary", "fallback_documentation"]
CompositeRightSelectionRule = Literal[
    "conveys_if_unprotected",
    "most_favorable_of_candidates",
    "realized_swap_outcome",
    "swap_if_target_not_protected",
    "more_favorable_of_primary_vs_secondary_pool",
]
CompositeFallbackTrigger = Literal[
    "primary_pick_non_conveyance",
    "swap_target_protected",
]

LAL_2027_PRIMARY_OBLIGATION_ID = "mem-pick-obligation:2026-02-03:lal-2027-r1-to-mem"
LAL_2027_FALLBACK_OBLIGATION_ID = "mem-pick-obligation:2026-02-03:lal-2027-r2-fallback-to-mem-doc"
ORL_2029_PRIMARY_OBLIGATION_ID = "mem-pick-obligation:2025-06-15:orl-2029-r1-swap-right"
ORL_2029_FALLBACK_OBLIGATION_ID = "mem-pick-obligation:2025-06-15:orl-2029-r2-fallback-doc"
UTH_2027_MOST_FAVORABLE_OBLIGATION_ID = "mem-pick-obligation:2026-02-03:uth-cle-min-2027-r1-most-favorable-to-mem"
PHX_2026_SWAP_PATH_OBLIGATION_ID = "mem-pick-obligation:2024-02-08:phx-2026-r1-swap-right"
PHX_2030_SWAP_LADDER_OBLIGATION_ID = "mem-pick-obligation:2023-07-11:phx-was-mem-2030-r1-swap-right"


class CompositePickFallbackBranch(BaseModel):
    obligation_id: str | None = None
    original_team_code: str
    round_number: int
    trigger_kind: CompositeFallbackTrigger
    protected_pick_start: int | None = None
    protected_pick_end: int | None = None
    projectable: Literal[False] = False


class CompositePickRight(BaseModel):
    family_id: str
    family_kind: CompositeRightKind
    obligation_role: CompositeRightRole = "primary"
    selection_rule: CompositeRightSelectionRule
    display_original_team_code: str | None = None
    route_team_code: str | None = None
    candidate_original_team_codes: list[str] = Field(default_factory=list)
    retained_original_team_codes: list[str] = Field(default_factory=list)
    secondary_candidate_original_team_codes: list[str] = Field(default_factory=list)
    protected_pick_start: int | None = None
    protected_pick_end: int | None = None
    related_obligation_ids: list[str] = Field(default_factory=list)
    fallback_branches: list[CompositePickFallbackBranch] = Field(default_factory=list)
    projectable: bool = True


def derive_composite_pick_right(
    *,
    source_obligation_id: str | None = None,
    draft_year: int | None = None,
    round_number: int | None = None,
    original_team_code: str | None = None,
) -> CompositePickRight | None:
    normalized_original_team_code = normalize_team_code(original_team_code)
    if source_obligation_id == LAL_2027_PRIMARY_OBLIGATION_ID:
        return build_lal_2027_protected_conveyance_right()
    if source_obligation_id == LAL_2027_FALLBACK_OBLIGATION_ID:
        return build_lal_2027_protected_conveyance_fallback()
    if source_obligation_id == ORL_2029_PRIMARY_OBLIGATION_ID:
        return build_orl_2029_protected_swap_right()
    if source_obligation_id == ORL_2029_FALLBACK_OBLIGATION_ID:
        return build_orl_2029_protected_swap_fallback()
    if source_obligation_id == UTH_2027_MOST_FAVORABLE_OBLIGATION_ID:
        return build_uth_2027_most_favorable_right()
    if source_obligation_id == PHX_2026_SWAP_PATH_OBLIGATION_ID:
        return build_phx_2026_realized_swap_path()
    if source_obligation_id == PHX_2030_SWAP_LADDER_OBLIGATION_ID:
        return build_phx_2030_tiered_swap_ladder()

    slot_key = (draft_year, round_number, normalized_original_team_code)
    if slot_key == (2026, 1, "PHX"):
        return build_phx_2026_realized_swap_path()
    if slot_key == (2027, 1, "LAL"):
        return build_lal_2027_protected_conveyance_right()
    if slot_key == (2027, 1, "UTH"):
        return build_uth_2027_most_favorable_right()
    if slot_key == (2029, 1, "ORL"):
        return build_orl_2029_protected_swap_right()
    if slot_key == (2030, 1, "PHX"):
        return build_phx_2030_tiered_swap_ladder()
    return None


def parse_pick_inventory_slot(pick_id: str) -> tuple[int | None, int | None, str | None]:
    parts = pick_id.split(":")
    if len(parts) < 6:
        return None, None, None
    round_part = parts[-2]
    if not round_part.startswith("r"):
        return None, None, None
    try:
        draft_year = int(parts[-3])
        round_number = int(round_part.removeprefix("r"))
    except ValueError:
        return None, None, None
    return draft_year, round_number, normalize_team_code(parts[-1]) or None


def normalize_team_code(value: str | None) -> str:
    return value.strip().upper() if value and value.strip() else ""


def build_lal_2027_protected_conveyance_right() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2027:r1:lal-protected-conveyance",
        family_kind="protected_conveyance",
        selection_rule="conveys_if_unprotected",
        display_original_team_code="LAL",
        candidate_original_team_codes=["LAL"],
        protected_pick_start=1,
        protected_pick_end=4,
        related_obligation_ids=[LAL_2027_FALLBACK_OBLIGATION_ID],
        fallback_branches=[
            CompositePickFallbackBranch(
                obligation_id=LAL_2027_FALLBACK_OBLIGATION_ID,
                original_team_code="LAL",
                round_number=2,
                trigger_kind="primary_pick_non_conveyance",
                protected_pick_start=1,
                protected_pick_end=4,
            )
        ],
    )


def build_lal_2027_protected_conveyance_fallback() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2027:r1:lal-protected-conveyance",
        family_kind="protected_conveyance",
        obligation_role="fallback_documentation",
        selection_rule="conveys_if_unprotected",
        display_original_team_code="LAL",
        candidate_original_team_codes=["LAL"],
        protected_pick_start=1,
        protected_pick_end=4,
        related_obligation_ids=[LAL_2027_PRIMARY_OBLIGATION_ID],
        projectable=False,
    )


def build_orl_2029_protected_swap_right() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2029:r1:orl-protected-swap",
        family_kind="protected_swap_right",
        selection_rule="swap_if_target_not_protected",
        display_original_team_code="ORL",
        candidate_original_team_codes=["ORL"],
        retained_original_team_codes=["MEM"],
        protected_pick_start=1,
        protected_pick_end=2,
        related_obligation_ids=[ORL_2029_FALLBACK_OBLIGATION_ID],
        fallback_branches=[
            CompositePickFallbackBranch(
                obligation_id=ORL_2029_FALLBACK_OBLIGATION_ID,
                original_team_code="ORL",
                round_number=2,
                trigger_kind="swap_target_protected",
                protected_pick_start=1,
                protected_pick_end=2,
            )
        ],
    )


def build_orl_2029_protected_swap_fallback() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2029:r1:orl-protected-swap",
        family_kind="protected_swap_right",
        obligation_role="fallback_documentation",
        selection_rule="swap_if_target_not_protected",
        display_original_team_code="ORL",
        candidate_original_team_codes=["ORL"],
        retained_original_team_codes=["MEM"],
        protected_pick_start=1,
        protected_pick_end=2,
        related_obligation_ids=[ORL_2029_PRIMARY_OBLIGATION_ID],
        projectable=False,
    )


def build_uth_2027_most_favorable_right() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2027:r1:uth-cle-min-most-favorable",
        family_kind="most_favorable_set",
        selection_rule="most_favorable_of_candidates",
        display_original_team_code="UTH",
        route_team_code="UTH",
        candidate_original_team_codes=["UTH", "CLE", "MIN"],
    )


def build_phx_2026_realized_swap_path() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2026:r1:phx-swap-path",
        family_kind="realized_swap_path",
        selection_rule="realized_swap_outcome",
        display_original_team_code="PHX",
        candidate_original_team_codes=["ORL", "PHX"],
        retained_original_team_codes=["MEM"],
    )


def build_phx_2030_tiered_swap_ladder() -> CompositePickRight:
    return CompositePickRight(
        family_id="family:mem:2030:r1:mem-phx-was-swap-ladder",
        family_kind="tiered_swap_ladder",
        selection_rule="more_favorable_of_primary_vs_secondary_pool",
        display_original_team_code="PHX",
        candidate_original_team_codes=["MEM"],
        secondary_candidate_original_team_codes=["PHX", "WAS"],
    )


class PlayerAsset(BaseModel):
    asset_id: str
    player_id: str
    display_name: str
    years_experience: int | None = None
    baseline_order: int | None = None
    kind: Literal["player"] = "player"


class PickAsset(BaseModel):
    asset_id: str
    pick_id: str
    original_team: str
    draft_year: int
    round_number: int
    protections: str | None = None
    swap_detail: str | None = None
    kind: Literal["pick"] = "pick"

    @computed_field
    @property
    def composite_right(self) -> CompositePickRight | None:
        return derive_composite_pick_right(
            draft_year=self.draft_year,
            round_number=self.round_number,
            original_team_code=self.original_team,
        )


class TransactionEvent(BaseModel):
    event_id: str
    event_type: EventType
    event_date: str
    label: str
    sequence: int = 0
    source_group_id: str | None = None


class AssetTransition(BaseModel):
    transition_id: str
    event_id: str
    asset_id: str
    transition_type: TransitionType
    from_state: str | None = None
    to_state: str | None = None
    notes: str | None = None


class FuturePickSnapshot(BaseModel):
    asset_id: str
    pick_id: str
    holding_status: str
    display_order: int | None = None
    source_obligation_id: str | None = None
    confidence: str | None = None
    notes: str | None = None

    @computed_field
    @property
    def composite_right(self) -> CompositePickRight | None:
        draft_year, round_number, original_team_code = parse_pick_inventory_slot(self.pick_id)
        return derive_composite_pick_right(
            source_obligation_id=self.source_obligation_id,
            draft_year=draft_year,
            round_number=round_number,
            original_team_code=original_team_code,
        )


class ConditionalPickBranchSnapshot(BaseModel):
    branch_id: str
    pick_ref: str
    asset_ref: str
    obligation_id: str | None = None
    original_team_code: str
    round_number: int
    trigger_kind: CompositeFallbackTrigger
    protected_pick_start: int | None = None
    protected_pick_end: int | None = None
    projectable: Literal[False] = False
    notes: str | None = None


class ConditionalPickFamilySnapshot(BaseModel):
    family_id: str
    family_kind: CompositeRightKind
    selection_rule: CompositeRightSelectionRule
    exclusivity_status: ConditionalPickFamilyStatus = "unresolved"
    display_original_team_code: str | None = None
    primary_pick_id: str
    primary_asset_id: str
    primary_source_obligation_id: str | None = None
    fallback_branches: list[ConditionalPickBranchSnapshot] = Field(default_factory=list)


class RosterSnapshot(BaseModel):
    snapshot_id: str
    as_of_date: str
    snapshot_kind: str | None = None
    season: str | None = None
    roster_asset_ids: list[str] = Field(default_factory=list)
    two_way_asset_ids: list[str] = Field(default_factory=list)
    future_pick_asset_ids: list[str] = Field(default_factory=list)
    future_picks: list[FuturePickSnapshot] = Field(default_factory=list)
    conditional_pick_families: list[ConditionalPickFamilySnapshot] = Field(default_factory=list)


class DailyRosterStatePlayer(BaseModel):
    asset_id: str
    player_id: str
    roster_status: Literal["standard", "two_way", "non_roster"] = "standard"
    depth_order: int | None = None
    is_two_way: bool = False
    is_standard_contract: bool = True


class DailyRosterState(BaseModel):
    state_id: str
    as_of_date: str
    season: str | None = None
    roster_asset_ids: list[str] = Field(default_factory=list)
    two_way_asset_ids: list[str] = Field(default_factory=list)
    player_states: list[DailyRosterStatePlayer] = Field(default_factory=list)


class DraftPriorOwnerLineage(BaseModel):
    draft_selection_id: str
    pick_id: str
    pick_asset_id: str
    player_id: str
    player_asset_id: str | None = None
    draft_year: int
    round_number: int
    pick_overall: int
    owner_team_code: str
    original_team_code: str
    source_obligation_id: str | None = None
    resolution_kind: str
    confidence: str
    notes: str | None = None


class DraftLotteryResultExport(BaseModel):
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
    pick_id: str | None = None
    pick_asset_id: str | None = None
    draft_selection_id: str | None = None
    draft_selection_player_id: str | None = None
    player_asset_id: str | None = None


class BaseGraphExport(BaseModel):
    franchise: str
    span_start: str
    span_end: str
    events: list[TransactionEvent] = Field(default_factory=list)
    player_assets: list[PlayerAsset] = Field(default_factory=list)
    pick_assets: list[PickAsset] = Field(default_factory=list)
    transitions: list[AssetTransition] = Field(default_factory=list)
    roster_snapshots: list[RosterSnapshot] = Field(default_factory=list)
    daily_roster_states: list[DailyRosterState] = Field(default_factory=list)
    draft_prior_owner_lineages: list[DraftPriorOwnerLineage] = Field(default_factory=list)
    draft_lottery_results: list[DraftLotteryResultExport] = Field(default_factory=list)


class FoundationExportInputs(BaseModel):
    """Typed, database-independent inputs for the base graph export assembly seam."""

    franchise: str = "memphis-grizzlies"
    span_start: str = "2016-07-01"
    # The offseason refresh is intentionally bounded by the dated source review.
    # Callers can still provide an earlier historical span explicitly.
    span_end: str = "2026-08-16"
    events: list[TransactionEvent] = Field(default_factory=list)
    player_assets: list[PlayerAsset] = Field(default_factory=list)
    pick_assets: list[PickAsset] = Field(default_factory=list)
    transitions: list[AssetTransition] = Field(default_factory=list)
    roster_snapshots: list[RosterSnapshot] = Field(default_factory=list)
    daily_roster_states: list[DailyRosterState] = Field(default_factory=list)
    draft_prior_owner_lineages: list[DraftPriorOwnerLineage] = Field(default_factory=list)
    draft_lottery_results: list[DraftLotteryResultExport] = Field(default_factory=list)

    @classmethod
    def from_base_graph_export(cls, export: BaseGraphExport) -> "FoundationExportInputs":
        return cls(**export.model_dump())


VisualizationLaneBand = Literal[
    "main_roster",
    "two_way",
    "temporary_overflow",
    "pick",
]
VisualizationOccupancyKind = Literal[
    "main_roster",
    "two_way",
    "temporary_overflow",
    "pick_owned",
    "pick_owed_out",
    "pick_swap_right",
    "pick_encumbered",
    "pick_conditional",
]
VisualizationSegmentKind = Literal[
    "resident",
    "event_lead_in",
    "event_settle_in",
    "draft_conversion",
    "termination",
]
VisualizationConnectorKind = Literal[
    "outgoing",
    "incoming",
    "conversion",
    "termination",
    "lane_shift",
]


class VisualizationTimeModel(BaseModel):
    unit: Literal["day"] = "day"
    scale: Literal["linear"] = "linear"
    compact_spacing: Literal["tight"] = "tight"


class VisualizationBandConfig(BaseModel):
    main_roster_slot_count: Literal[15] = 15
    two_way_slot_count: Literal[3] = 3
    has_temporary_overflow_band: Literal[True] = True
    has_pick_band: Literal[True] = True


class VisualizationLane(BaseModel):
    lane_id: str
    band: VisualizationLaneBand
    slot_index: int
    visual_order: int
    is_dynamic: bool
    label: str


class VisualizationPlayerMarker(BaseModel):
    marker_type: Literal["player"] = "player"
    display_name: str
    headshot_url: str | None = None


class VisualizationPickMarker(BaseModel):
    marker_type: Literal["pick"] = "pick"
    chip_label: str


VisualizationAssetMarker = Annotated[
    VisualizationPlayerMarker | VisualizationPickMarker,
    Field(discriminator="marker_type"),
]


class VisualizationAsset(BaseModel):
    asset_id: str
    asset_kind: AssetKind
    marker: VisualizationAssetMarker
    display_label: str
    foundation_asset_id: str
    player_id: str | None = None
    pick_id: str | None = None

    @model_validator(mode="after")
    def validate_identity_fields(self) -> "VisualizationAsset":
        if self.asset_kind == "player":
            if self.player_id is None:
                raise ValueError("player assets require player_id")
            if self.pick_id is not None:
                raise ValueError("player assets must not set pick_id")
            if self.marker.marker_type != "player":
                raise ValueError("player assets require a player marker")
        if self.asset_kind == "pick":
            if self.pick_id is None:
                raise ValueError("pick assets require pick_id")
            if self.player_id is not None:
                raise ValueError("pick assets must not set player_id")
            if self.marker.marker_type != "pick":
                raise ValueError("pick assets require a pick marker")
        return self


class VisualizationOccupancyInterval(BaseModel):
    interval_id: str
    asset_id: str
    lane_id: str
    start_date: str
    end_date: str
    occupancy_kind: VisualizationOccupancyKind
    source_state_id: str | None = None
    source_snapshot_id: str | None = None
    source_obligation_id: str | None = None


class VisualizationEventSummary(BaseModel):
    sent_asset_ids: list[str] = Field(default_factory=list)
    received_asset_ids: list[str] = Field(default_factory=list)
    sent_label: str | None = None
    received_label: str | None = None


class VisualizationEventNode(BaseModel):
    node_id: str
    canonical_event_id: str
    source_group_id: str | None = None
    event_type: EventType
    event_date: str
    sequence: int
    compact_label: str
    detail_label: str | None = None
    summary: VisualizationEventSummary | None = None
    inbound_asset_ids: list[str] = Field(default_factory=list)
    outbound_asset_ids: list[str] = Field(default_factory=list)


class VisualizationStrandSegment(BaseModel):
    segment_id: str
    asset_id: str
    lane_id: str
    segment_kind: VisualizationSegmentKind
    start_date: str
    end_date: str
    start_node_id: str | None = None
    end_node_id: str | None = None


class VisualizationEventConnector(BaseModel):
    connector_id: str
    node_id: str
    asset_id: str
    connector_kind: VisualizationConnectorKind
    from_lane_id: str | None = None
    to_lane_id: str | None = None
    lead_window_days: int
    settle_window_days: int


class VisualizationConditionalPickBranch(BaseModel):
    branch_id: str
    original_team_code: str
    round_number: int
    trigger_kind: str
    projectable: Literal[False] = False
    notes: str | None = None


class VisualizationConditionalPickFamily(BaseModel):
    family_id: str
    family_kind: str
    selection_rule: str
    exclusivity_status: ConditionalPickFamilyStatus = "unresolved"
    primary_pick_id: str
    primary_asset_id: str
    fallback_branches: list[VisualizationConditionalPickBranch] = Field(default_factory=list)


class VisualizationDraftLotteryContext(BaseModel):
    lottery_result_id: str
    draft_year: int
    lottery_date: str | None = None
    original_team_code: str | None = None
    owner_team_code: str | None = None
    result_pick_slot: int
    pick_id: str | None = None
    pick_asset_id: str | None = None
    draft_selection_id: str | None = None


class VisualizationAdditiveContext(BaseModel):
    conditional_pick_families: list[VisualizationConditionalPickFamily] = Field(default_factory=list)
    draft_lottery_results: list[VisualizationDraftLotteryContext] = Field(default_factory=list)


class VisualizationExportV1(BaseModel):
    schema_version: Literal["visualization_export_v1"] = "visualization_export_v1"
    franchise: Literal["MEM"] = "MEM"
    generated_at: str
    source_span_start: str
    source_span_end: str
    render_span_start: str
    render_span_end: str
    time_model: VisualizationTimeModel = Field(default_factory=VisualizationTimeModel)
    band_config: VisualizationBandConfig = Field(default_factory=VisualizationBandConfig)
    lanes: list[VisualizationLane] = Field(default_factory=list)
    assets: list[VisualizationAsset] = Field(default_factory=list)
    occupancy_intervals: list[VisualizationOccupancyInterval] = Field(default_factory=list)
    event_nodes: list[VisualizationEventNode] = Field(default_factory=list)
    strand_segments: list[VisualizationStrandSegment] = Field(default_factory=list)
    event_connectors: list[VisualizationEventConnector] = Field(default_factory=list)
    additive_context: VisualizationAdditiveContext = Field(default_factory=VisualizationAdditiveContext)

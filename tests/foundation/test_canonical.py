from foundation.canonical import (
    canonicalize_event_type,
    derive_foundation_canonical_bundle,
)
from foundation.ingest import SourceEventRow, build_foundation_ingest_sample_bundle


def test_canonicalize_event_type_uses_graph_facing_set() -> None:
    assert canonicalize_event_type("trade") == "trade"
    assert canonicalize_event_type("draft") == "draft"
    assert canonicalize_event_type("conversion") == "signing"
    assert canonicalize_event_type("release") == "waiver"


def test_derive_foundation_canonical_bundle_from_sample_source_events() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    canonical = derive_foundation_canonical_bundle(bundle.source_events)
    assert canonical.canonical_events
    assert canonical.canonical_event_members
    assert canonical.event_asset_transitions
    assert len(canonical.canonical_event_members) == len(bundle.source_events)


def test_trade_grouping_and_transition_derivation_behave_minimally() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    canonical = derive_foundation_canonical_bundle(bundle.source_events)
    grouped_trades = [row for row in canonical.canonical_events if row.event_type == "trade"]
    assert grouped_trades
    transitions = canonical.event_asset_transitions
    assert any(row.transition_type == "acquired" and row.direction == "in" for row in transitions)
    assert any(row.transition_type == "departed" and row.direction == "out" for row in transitions)


def test_canonical_transition_derivation_respects_player_alias_lookup() -> None:
    source_events = [
        SourceEventRow(
            source_event_id="bref:mem:2024:2023-12-18:1:1",
            source_record_id="bref:mem:2024:2023-12-18:1",
            event_date="2023-12-18",
            event_type="waiver",
            label="Memphis waived Kenny Lofton Jr",
            team_scope="memphis-grizzlies",
            source_group_hint=None,
            normalized_payload={
                "player_names_in": [],
                "player_names_out": ["Kenny Lofton Jr"],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        )
    ]
    canonical = derive_foundation_canonical_bundle(
        source_events,
        player_id_by_alias={"kenny lofton jr": "player:kenneth-lofton-jr"},
    )
    assert canonical.event_asset_transitions[0].asset_id == "asset:player:kenneth-lofton-jr"


def test_canonical_transition_derivation_skips_unresolved_pick_text() -> None:
    source_events = [
        SourceEventRow(
            source_event_id="bref:mem:2024:2023-07-01:1:1",
            source_record_id="bref:mem:2024:2023-07-01:1",
            event_date="2023-07-01",
            event_type="trade",
            label="Memphis traded unresolved draft consideration",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2023-07-01:trade",
            normalized_payload={
                "player_names_in": [],
                "player_names_out": [],
                "pick_details_in": [
                    {"raw_text": "future second-round pick", "draft_year": None, "round_number": None}
                ],
                "pick_details_out": [],
            },
        )
    ]
    canonical = derive_foundation_canonical_bundle(source_events)
    assert canonical.event_asset_transitions == []

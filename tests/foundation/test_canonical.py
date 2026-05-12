from foundation.canonical import (
    canonicalize_event_type,
    derive_foundation_canonical_bundle,
)
from foundation.ingest import build_foundation_ingest_sample_bundle


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

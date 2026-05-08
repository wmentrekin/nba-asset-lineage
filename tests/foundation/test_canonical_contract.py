from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any

import pytest

from foundation.ingest import (
    SourceEventRow,
    build_pick_id,
    derive_foundation_entities_from_source_events,
)


def _canonical_builder() -> Any:
    candidate_modules = ("foundation.canonical", "foundation.ingest")
    candidate_names = (
        "build_canonical_layer_from_source_events",
        "derive_canonical_layer_from_source_events",
        "build_canonical_layer",
        "derive_canonical_layer",
    )
    for module_name in candidate_modules:
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            continue
        for name in candidate_names:
            builder = getattr(module, name, None)
            if callable(builder):
                return builder

    pytest.xfail("canonical layer runtime is not implemented yet")


def _invoke_canonical_builder(source_events: list[SourceEventRow]) -> dict[str, list[dict[str, Any]]]:
    builder = _canonical_builder()
    derived = derive_foundation_entities_from_source_events(source_events)
    signature = inspect.signature(builder)

    kwargs: dict[str, Any] = {}
    if "source_events" in signature.parameters:
        kwargs["source_events"] = source_events
    if "players" in signature.parameters:
        kwargs["players"] = derived.players
    if "picks" in signature.parameters:
        kwargs["picks"] = derived.picks
    if "assets" in signature.parameters:
        kwargs["assets"] = derived.assets

    result = builder(**kwargs) if kwargs else builder(source_events)
    return _normalize_canonical_result(result)


def _normalize_canonical_result(result: Any) -> dict[str, list[dict[str, Any]]]:
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    if not isinstance(payload, dict):
        raise AssertionError("canonical layer builder must return a mapping-like result")

    canonical_events = payload.get("canonical_events") or payload.get("events") or []
    members = payload.get("canonical_event_members") or payload.get("members") or []
    transitions = payload.get("event_asset_transitions") or payload.get("transitions") or []

    return {
        "canonical_events": [_row_to_dict(row) for row in canonical_events],
        "canonical_event_members": [_row_to_dict(row) for row in members],
        "event_asset_transitions": [_row_to_dict(row) for row in transitions],
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        return row.model_dump(mode="json")
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    raise AssertionError(f"unsupported canonical row type: {type(row)!r}")


def _member_source_event_ids(
    members: list[dict[str, Any]],
    canonical_event_id: str,
) -> set[str]:
    source_event_ids: set[str] = set()
    for row in members:
        if row.get("canonical_event_id") != canonical_event_id:
            continue
        source_event_id = row.get("source_event_id")
        if isinstance(source_event_id, str):
            source_event_ids.add(source_event_id)
    return source_event_ids


def _transition_asset_ids_by_direction(
    transitions: list[dict[str, Any]],
    canonical_event_id: str,
    direction: str,
) -> set[str]:
    asset_ids: set[str] = set()
    for row in transitions:
        if row.get("canonical_event_id") != canonical_event_id:
            continue
        if row.get("direction") != direction:
            continue
        asset_id = row.get("asset_id")
        if isinstance(asset_id, str):
            asset_ids.add(asset_id)
    return asset_ids


def test_non_trade_same_day_source_events_stay_separate_canonical_events() -> None:
    source_events = [
        SourceEventRow(
            source_event_id="bref:mem:2024-01-10:conversion",
            source_record_id="bref:mem:2024-01-10",
            event_date="2024-01-10",
            event_type="conversion",
            label="Memphis converted Vince Williams Jr",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2024-01-10:conversion",
            normalized_payload={
                "player_names_in": ["Vince Williams Jr"],
                "player_names_out": [],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        ),
        SourceEventRow(
            source_event_id="bref:mem:2024-01-10:waiver",
            source_record_id="bref:mem:2024-01-10",
            event_date="2024-01-10",
            event_type="waiver",
            label="Memphis waived Bismack Biyombo",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2024-01-10:waiver",
            normalized_payload={
                "player_names_in": [],
                "player_names_out": ["Bismack Biyombo"],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        ),
    ]

    result = _invoke_canonical_builder(source_events)

    assert len(result["canonical_events"]) == 2
    for canonical_event in result["canonical_events"]:
        canonical_event_id = canonical_event["canonical_event_id"]
        assert _member_source_event_ids(result["canonical_event_members"], canonical_event_id) in (
            {"bref:mem:2024-01-10:conversion"},
            {"bref:mem:2024-01-10:waiver"},
        )
        assert canonical_event.get("is_grouped_event") in (False, None)


def test_same_day_trade_source_events_group_into_one_canonical_trade() -> None:
    source_events = [
        SourceEventRow(
            source_event_id="bref:mem:2026-02-05:1",
            source_record_id="bref:mem:2026-02-05",
            event_date="2026-02-05",
            event_type="trade",
            label="Memphis trade fragment one",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2026-02-05:trade-group",
            normalized_payload={
                "player_names_in": ["Marcus Smart"],
                "player_names_out": ["Luke Kennard"],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        ),
        SourceEventRow(
            source_event_id="bref:mem:2026-02-05:2",
            source_record_id="bref:mem:2026-02-05",
            event_date="2026-02-05",
            event_type="trade",
            label="Memphis trade fragment two",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2026-02-05:trade-group",
            normalized_payload={
                "player_names_in": ["Jake LaRavia"],
                "player_names_out": ["John Konchar"],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        ),
    ]

    result = _invoke_canonical_builder(source_events)

    assert len(result["canonical_events"]) == 1
    canonical_event = result["canonical_events"][0]
    assert canonical_event.get("event_type") == "trade"
    assert canonical_event.get("is_grouped_event") in (True, None)
    assert _member_source_event_ids(
        result["canonical_event_members"],
        canonical_event["canonical_event_id"],
    ) == {
        "bref:mem:2026-02-05:1",
        "bref:mem:2026-02-05:2",
    }


def test_event_asset_transition_uses_grouped_member_payload_directionality() -> None:
    source_events = [
        SourceEventRow(
            source_event_id="bref:mem:2026-02-05:1",
            source_record_id="bref:mem:2026-02-05",
            event_date="2026-02-05",
            event_type="trade",
            label="Memphis trade fragment one",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2026-02-05:trade-group",
            normalized_payload={
                "player_names_in": ["Marcus Smart"],
                "player_names_out": ["Luke Kennard"],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        ),
        SourceEventRow(
            source_event_id="bref:mem:2026-02-05:2",
            source_record_id="bref:mem:2026-02-05",
            event_date="2026-02-05",
            event_type="trade",
            label="Memphis trade fragment two",
            team_scope="memphis-grizzlies",
            source_group_hint="bref:2026-02-05:trade-group",
            normalized_payload={
                "player_names_in": [],
                "player_names_out": ["John Konchar"],
                "pick_details_in": [
                    {
                        "raw_text": "2028 first-round pick (via Phoenix)",
                        "draft_year": 2028,
                        "round_number": 1,
                        "original_team": "PHX",
                        "protection_text": None,
                        "swap_text": None,
                    }
                ],
                "pick_details_out": [],
            },
        ),
    ]

    result = _invoke_canonical_builder(source_events)

    assert len(result["canonical_events"]) == 1
    canonical_event_id = result["canonical_events"][0]["canonical_event_id"]
    in_asset_ids = _transition_asset_ids_by_direction(
        result["event_asset_transitions"],
        canonical_event_id,
        "in",
    )
    out_asset_ids = _transition_asset_ids_by_direction(
        result["event_asset_transitions"],
        canonical_event_id,
        "out",
    )

    assert in_asset_ids >= {
        "asset:player:marcus-smart",
        f"asset:pick:{build_pick_id('2028 first-round pick (via Phoenix)')}",
    }
    assert out_asset_ids >= {
        "asset:player:luke-kennard",
        "asset:player:john-konchar",
    }

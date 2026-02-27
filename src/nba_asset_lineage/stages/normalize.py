from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from nba_asset_lineage.files import read_csv, write_csv
from nba_asset_lineage.ids import deterministic_asset_id, deterministic_edge_id, deterministic_event_id
from nba_asset_lineage.settings import (
    ALLOWED_ACTIONS,
    ALLOWED_EVENT_TYPES,
    DEFAULT_TEAM_NAME,
    END_STATE_NODE_PREFIX,
    INGESTED_RAW_DIR,
    PROCESSED_DIR,
    START_STATE_NODE_PREFIX,
)


@dataclass
class OpenAssetState:
    asset_id: str
    asset_key: str
    attrs: dict[str, str]
    open_source_node_id: str
    open_start_date: str
    segment_index: int


def _event_sort_key(row: dict[str, str]) -> tuple[str, str]:
    return row["event_date"], row["event_key"]


def _build_state_node_id(prefix: str, team_code: str, date_value: str) -> str:
    compact = date_value.replace("-", "")
    return f"{prefix}_{team_code.lower()}_{compact}"


def _close_segment(
    segments: list[dict[str, str]],
    state: OpenAssetState,
    target_node_id: str,
    end_date: str,
    is_active_at_end: str,
    prior_transactions: list[str],
) -> None:
    edge_id = deterministic_edge_id(
        asset_id=state.asset_id,
        source_node_id=state.open_source_node_id,
        target_node_id=target_node_id,
        segment_index=state.segment_index,
    )
    row = {
        "edge_id": edge_id,
        "asset_id": state.asset_id,
        "asset_key": state.asset_key,
        "asset_type": state.attrs.get("asset_type", ""),
        "subtype": state.attrs.get("subtype", ""),
        "source_node_id": state.open_source_node_id,
        "target_node_id": target_node_id,
        "start_date": state.open_start_date,
        "end_date": end_date,
        "is_active_at_end": is_active_at_end,
        "player_name": state.attrs.get("player_name", ""),
        "contract_expiry_year": state.attrs.get("contract_expiry_year", ""),
        "average_annual_salary": state.attrs.get("average_annual_salary", ""),
        "acquisition_method": state.attrs.get("acquisition_method", ""),
        "original_team": state.attrs.get("original_team", ""),
        "pick_year": state.attrs.get("pick_year", ""),
        "pick_number": state.attrs.get("pick_number", ""),
        "protections_raw": state.attrs.get("protections_raw", ""),
        "protections_structured": state.attrs.get("protections_structured", ""),
        "swap_conditions_raw": state.attrs.get("swap_conditions_raw", ""),
        "swap_conditions_structured": state.attrs.get("swap_conditions_structured", ""),
        "prior_transactions": json.dumps(prior_transactions),
    }
    segments.append(row)


def _asset_attrs_from_row(row: dict[str, str], fallback: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(fallback or {})
    for key in (
        "asset_type",
        "subtype",
        "player_name",
        "contract_expiry_year",
        "average_annual_salary",
        "acquisition_method",
        "original_team",
        "pick_year",
        "pick_number",
        "protections_raw",
        "protections_structured",
        "swap_conditions_raw",
        "swap_conditions_structured",
    ):
        value = row.get(key, "")
        if value:
            merged[key] = value
    return merged


def run_normalize(context: dict[str, str]) -> None:
    team_code = context["team_code"]
    start_date = context["start_date"]
    end_date = context["end_date"]

    start_node_id = _build_state_node_id(START_STATE_NODE_PREFIX, team_code, start_date)
    end_node_id = _build_state_node_id(END_STATE_NODE_PREFIX, team_code, end_date)

    initial_assets = read_csv(INGESTED_RAW_DIR / "initial_assets.csv")
    events = read_csv(INGESTED_RAW_DIR / "events.csv")
    event_assets = read_csv(INGESTED_RAW_DIR / "event_assets.csv")
    sources = read_csv(INGESTED_RAW_DIR / "sources.csv")

    source_by_id = {row["source_id"]: row for row in sources}
    event_assets_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in event_assets:
        event_assets_by_key[row["event_key"]].append(row)

    normalized_events: list[dict[str, str]] = []
    for event in sorted(events, key=_event_sort_key):
        event_type = event["event_type"].strip().lower()
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unsupported event_type: {event_type}")

        if not (start_date <= event["event_date"] <= end_date):
            continue

        source = source_by_id.get(event["source_id"], {})
        event_id = deterministic_event_id(
            team_code=team_code,
            event_key=event["event_key"],
            event_date=event["event_date"],
            event_type=event_type,
        )
        normalized_events.append(
            {
                "event_id": event_id,
                "event_key": event["event_key"],
                "event_date": event["event_date"],
                "event_type": event_type,
                "event_label": event.get("event_label", ""),
                "description": event.get("description", ""),
                "source_id": event.get("source_id", ""),
                "source_name": source.get("source_name", ""),
                "source_url": source.get("source_url", ""),
            }
        )

    event_id_by_key = {row["event_key"]: row["event_id"] for row in normalized_events}
    active_assets: dict[str, OpenAssetState] = {}
    asset_transaction_history: dict[str, list[str]] = defaultdict(list)
    asset_catalog: dict[str, dict[str, str]] = {}
    segments: list[dict[str, str]] = []
    event_asset_links: list[dict[str, str]] = []

    for row in initial_assets:
        asset_key = row["asset_key"]
        asset_id = deterministic_asset_id(team_code, asset_key)
        attrs = _asset_attrs_from_row(row)
        active_assets[asset_key] = OpenAssetState(
            asset_id=asset_id,
            asset_key=asset_key,
            attrs=attrs,
            open_source_node_id=start_node_id,
            open_start_date=start_date,
            segment_index=0,
        )
        asset_transaction_history[asset_id].append(f"{start_date}|initial_state|held")
        asset_catalog[asset_id] = {
            "asset_id": asset_id,
            "asset_key": asset_key,
            "asset_type": attrs.get("asset_type", ""),
            "subtype": attrs.get("subtype", ""),
            "team_code": team_code,
            "team_name": DEFAULT_TEAM_NAME,
        }

    for event in normalized_events:
        event_key = event["event_key"]
        event_id = event["event_id"]
        event_date = event["event_date"]
        rows = event_assets_by_key.get(event_key, [])

        for row in rows:
            action = row["action"].strip().lower()
            if action not in ALLOWED_ACTIONS:
                raise ValueError(f"Unsupported action '{action}' for event {event_key}")

            asset_key = row["asset_key"]
            asset_id = deterministic_asset_id(team_code, asset_key)
            history = asset_transaction_history[asset_id]

            # Deterministic safety net: if a relinquish/modify row appears before explicit
            # acquisition history is populated, bootstrap the asset from the start boundary.
            if action in {"relinquish", "terminate", "modify"} and asset_key not in active_assets:
                bootstrap_attrs = _asset_attrs_from_row(row)
                active_assets[asset_key] = OpenAssetState(
                    asset_id=asset_id,
                    asset_key=asset_key,
                    attrs=bootstrap_attrs,
                    open_source_node_id=start_node_id,
                    open_start_date=start_date,
                    segment_index=0,
                )
                if not history:
                    history.append(f"{start_date}|bootstrap_from_event|held")
                if asset_id not in asset_catalog:
                    asset_catalog[asset_id] = {
                        "asset_id": asset_id,
                        "asset_key": asset_key,
                        "asset_type": bootstrap_attrs.get("asset_type", ""),
                        "subtype": bootstrap_attrs.get("subtype", ""),
                        "team_code": team_code,
                        "team_name": DEFAULT_TEAM_NAME,
                    }

            if action in {"relinquish", "terminate", "modify"} and asset_key in active_assets:
                state = active_assets[asset_key]
                _close_segment(
                    segments=segments,
                    state=state,
                    target_node_id=event_id,
                    end_date=event_date,
                    is_active_at_end="false",
                    prior_transactions=history,
                )

            if action == "relinquish" or action == "terminate":
                if asset_key in active_assets:
                    del active_assets[asset_key]

            if action == "acquire" or action == "modify":
                prior_attrs = active_assets[asset_key].attrs if asset_key in active_assets else {}
                next_attrs = _asset_attrs_from_row(row, prior_attrs)

                previous_index = active_assets[asset_key].segment_index if asset_key in active_assets else -1
                next_state = OpenAssetState(
                    asset_id=asset_id,
                    asset_key=asset_key,
                    attrs=next_attrs,
                    open_source_node_id=event_id,
                    open_start_date=event_date,
                    segment_index=previous_index + 1,
                )
                active_assets[asset_key] = next_state

                asset_catalog[asset_id] = {
                    "asset_id": asset_id,
                    "asset_key": asset_key,
                    "asset_type": next_attrs.get("asset_type", ""),
                    "subtype": next_attrs.get("subtype", ""),
                    "team_code": team_code,
                    "team_name": DEFAULT_TEAM_NAME,
                }

            direction = "incoming" if action in {"relinquish", "terminate"} else "outgoing"
            event_asset_links.append(
                {
                    "event_id": event_id,
                    "event_key": event_key,
                    "asset_id": asset_id,
                    "asset_key": asset_key,
                    "action": action,
                    "direction": direction,
                }
            )
            history.append(f"{event_date}|{event['event_type']}|{action}")

    for asset_key, state in sorted(active_assets.items(), key=lambda item: item[0]):
        _close_segment(
            segments=segments,
            state=state,
            target_node_id=end_node_id,
            end_date="",
            is_active_at_end="true",
            prior_transactions=asset_transaction_history[state.asset_id],
        )

    write_csv(
        PROCESSED_DIR / "events.csv",
        sorted(normalized_events, key=lambda row: (row["event_date"], row["event_id"])),
        [
            "event_id",
            "event_key",
            "event_date",
            "event_type",
            "event_label",
            "description",
            "source_id",
            "source_name",
            "source_url",
        ],
    )

    write_csv(
        PROCESSED_DIR / "asset_segments.csv",
        sorted(segments, key=lambda row: (row["asset_id"], row["start_date"], row["edge_id"])),
        [
            "edge_id",
            "asset_id",
            "asset_key",
            "asset_type",
            "subtype",
            "source_node_id",
            "target_node_id",
            "start_date",
            "end_date",
            "is_active_at_end",
            "player_name",
            "contract_expiry_year",
            "average_annual_salary",
            "acquisition_method",
            "original_team",
            "pick_year",
            "pick_number",
            "protections_raw",
            "protections_structured",
            "swap_conditions_raw",
            "swap_conditions_structured",
            "prior_transactions",
        ],
    )

    write_csv(
        PROCESSED_DIR / "assets.csv",
        sorted(asset_catalog.values(), key=lambda row: row["asset_id"]),
        ["asset_id", "asset_key", "asset_type", "subtype", "team_code", "team_name"],
    )

    write_csv(
        PROCESSED_DIR / "event_asset_links.csv",
        sorted(event_asset_links, key=lambda row: (row["event_id"], row["asset_id"], row["action"])),
        ["event_id", "event_key", "asset_id", "asset_key", "action", "direction"],
    )

    write_csv(
        PROCESSED_DIR / "state_nodes.csv",
        [
            {
                "node_id": start_node_id,
                "node_type": "state_boundary",
                "label": f"Memphis Start State {start_date}",
                "event_date": start_date,
            },
            {
                "node_id": end_node_id,
                "node_type": "state_boundary",
                "label": f"Memphis End State {end_date}",
                "event_date": end_date,
            },
        ],
        ["node_id", "node_type", "label", "event_date"],
    )

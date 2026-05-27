from __future__ import annotations

from datetime import date
from pathlib import Path

import foundation.daily_roster_state as daily_roster_state
from foundation.daily_roster_state import (
    build_daily_roster_state_rows,
    load_daily_roster_state,
    preview_daily_roster_state,
)
from foundation.ingest import PlayerAliasRow, RosterBaselinePlayerRow, SourceEventRow
from foundation.two_way_status import TwoWayStatusFixture, TwoWayStatusFixtureRow


def make_baseline(
    *,
    season: str = "2023-24",
    player_id: str,
    display_name: str,
    roster_order: int,
) -> RosterBaselinePlayerRow:
    return RosterBaselinePlayerRow(
        season=season,
        team_code="MEM",
        player_id=player_id,
        display_name=display_name,
        source_record_id="bref:mem:2024:roster",
        roster_order=roster_order,
    )


def make_event(
    *,
    source_event_id: str,
    event_date: str,
    event_type: str,
    inbound: list[str] | None = None,
    outbound: list[str] | None = None,
) -> SourceEventRow:
    return SourceEventRow(
        source_event_id=source_event_id,
        source_record_id=f"source-record:{source_event_id}",
        event_date=event_date,
        event_type=event_type,
        label=source_event_id,
        team_scope="memphis-grizzlies",
        source_group_hint=None,
        normalized_payload={
            "player_names_in": inbound or [],
            "player_names_out": outbound or [],
            "pick_details_in": [],
            "pick_details_out": [],
        },
    )


def make_two_way_fixture(*rows: TwoWayStatusFixtureRow) -> TwoWayStatusFixture:
    return TwoWayStatusFixture(
        fixture_id="seed_v1",
        team_code="MEM",
        coverage_start=date(2017, 7, 1),
        coverage_end=None,
        coverage_statement="test fixture",
        source_set=[{"label": "test", "locator": "https://example.test"}],
        confidence_rubric={"high": ["official"], "medium": ["secondary"], "low": ["ambiguous"]},
        rows=list(rows),
    )


def make_two_way_row(
    *,
    status_id: str = "tw:1",
    player_name: str = "Javon Small",
    player_id: str | None = "player:javon-small-tw",
    start_date: date = date(2024, 1, 10),
    end_date: date | None = date(2024, 1, 12),
) -> TwoWayStatusFixtureRow:
    return TwoWayStatusFixtureRow(
        status_id=status_id,
        player_name=player_name,
        player_id=player_id,
        team_code="MEM",
        start_date=start_date,
        end_date=end_date,
        source_urls=["https://example.test/two-way"],
        confidence="high",
        loadable=True,
    )


def player_ids_for_date(
    rows: list[daily_roster_state.DailyRosterStatePlayerRow],
    target_date: date,
) -> list[str]:
    return [row.player_id for row in rows if row.state_date == target_date]


def row_for_date(
    rows: list[daily_roster_state.DailyRosterStateRow],
    target_date: date,
) -> daily_roster_state.DailyRosterStateRow:
    return next(row for row in rows if row.state_date == target_date)


def test_build_daily_roster_state_carries_forward_quiet_days() -> None:
    baselines = [
        make_baseline(player_id="player:incumbent", display_name="Incumbent", roster_order=1),
        make_baseline(player_id="player:later-arrival", display_name="Later Arrival", roster_order=2),
    ]
    source_events = [
        make_event(
            source_event_id="event:signing:later-arrival",
            event_date="2024-01-10",
            event_type="signing",
            inbound=["Later Arrival"],
        )
    ]

    rows, player_rows = build_daily_roster_state_rows(
        baselines,
        source_events=source_events,
        fixture_path=None,
    )

    assert player_ids_for_date(player_rows, date(2024, 1, 9)) == ["player:incumbent"]
    assert player_ids_for_date(player_rows, date(2024, 1, 10)) == ["player:incumbent", "player:later-arrival"]
    assert player_ids_for_date(player_rows, date(2024, 1, 11)) == ["player:incumbent", "player:later-arrival"]
    assert row_for_date(rows, date(2024, 1, 11)).event_count == 0


def test_build_daily_roster_state_applies_waiver_signing_and_trade_effects() -> None:
    baselines = [
        make_baseline(player_id="player:incumbent", display_name="Incumbent", roster_order=1),
        make_baseline(player_id="player:trade-away", display_name="Trade Away", roster_order=2),
        make_baseline(player_id="player:waived-player", display_name="Waived Player", roster_order=3),
    ]
    source_events = [
        make_event(
            source_event_id="event:trade",
            event_date="2024-02-08",
            event_type="trade",
            inbound=["Trade Return"],
            outbound=["Trade Away"],
        ),
        make_event(
            source_event_id="event:waiver",
            event_date="2024-02-10",
            event_type="waiver",
            outbound=["Waived Player"],
        ),
        make_event(
            source_event_id="event:signing",
            event_date="2024-02-12",
            event_type="signing",
            inbound=["Free Agent"],
        ),
    ]
    aliases = [
        PlayerAliasRow(
            alias_id="alias:trade-return",
            player_id="player:trade-return",
            source_system="manual",
            alias_name="Trade Return",
            normalized_alias_name="trade return",
            is_manual=True,
        ),
        PlayerAliasRow(
            alias_id="alias:free-agent",
            player_id="player:free-agent",
            source_system="manual",
            alias_name="Free Agent",
            normalized_alias_name="free agent",
            is_manual=True,
        ),
    ]

    rows, player_rows = build_daily_roster_state_rows(
        baselines,
        source_events=source_events,
        player_aliases=aliases,
        fixture_path=None,
    )

    assert player_ids_for_date(player_rows, date(2024, 2, 7)) == [
        "player:incumbent",
        "player:trade-away",
        "player:waived-player",
    ]
    assert player_ids_for_date(player_rows, date(2024, 2, 8)) == [
        "player:incumbent",
        "player:waived-player",
        "player:trade-return",
    ]
    assert player_ids_for_date(player_rows, date(2024, 2, 10)) == [
        "player:incumbent",
        "player:trade-return",
    ]
    assert player_ids_for_date(player_rows, date(2024, 2, 12)) == [
        "player:incumbent",
        "player:trade-return",
        "player:free-agent",
    ]
    assert row_for_date(rows, date(2024, 2, 8)).source_event_ids == ["event:trade"]


def test_preview_daily_roster_state_applies_two_way_intervals(monkeypatch) -> None:
    baselines = [
        make_baseline(
            season="2024-25",
            player_id="player:javon-small-tw",
            display_name="Javon Small (TW)",
            roster_order=1,
        )
    ]
    fixture = make_two_way_fixture(
        make_two_way_row(
            start_date=date(2025, 1, 10),
            end_date=date(2025, 1, 12),
        )
    )

    monkeypatch.setattr(daily_roster_state, "load_roster_baseline_players_from_database", lambda database_url: baselines)
    monkeypatch.setattr(daily_roster_state, "load_source_events_from_database", lambda database_url: [])
    monkeypatch.setattr(daily_roster_state, "load_player_aliases_from_database", lambda database_url: [])
    monkeypatch.setattr(daily_roster_state, "load_roster_snapshot_anchors_from_database", lambda database_url, team_code="MEM": [])
    monkeypatch.setattr(daily_roster_state, "load_two_way_status_fixture", lambda path: fixture)

    preview = preview_daily_roster_state("postgresql://example.test/db", fixture_path=Path("fixture.json"))

    jan_10 = [
        row
        for row in preview.player_rows
        if row.state_date == date(2025, 1, 10)
    ]
    jan_12 = [
        row
        for row in preview.player_rows
        if row.state_date == date(2025, 1, 12)
    ]

    assert preview.blocked_rows == 0
    assert len(jan_10) == 1
    assert jan_10[0].roster_status == "two_way"
    assert jan_10[0].is_standard_contract is False
    assert len(jan_12) == 1
    assert jan_12[0].roster_status == "standard"


def test_load_daily_roster_state_dry_run_returns_projected_counts(monkeypatch) -> None:
    baselines = [
        make_baseline(player_id="player:incumbent", display_name="Incumbent", roster_order=1),
    ]

    monkeypatch.setattr(daily_roster_state, "load_roster_baseline_players_from_database", lambda database_url: baselines)
    monkeypatch.setattr(daily_roster_state, "load_source_events_from_database", lambda database_url: [])
    monkeypatch.setattr(daily_roster_state, "load_player_aliases_from_database", lambda database_url: [])
    monkeypatch.setattr(daily_roster_state, "load_roster_snapshot_anchors_from_database", lambda database_url, team_code="MEM": [])

    result = load_daily_roster_state(
        "postgresql://example.test/db",
        fixture_path=None,
        dry_run=True,
    )

    assert result.blocked_rows == 0
    assert result.reset_state_rows == 366
    assert result.applied_state_rows == 366
    assert result.applied_player_rows == 366


def test_build_daily_roster_state_uses_snapshot_anchors_without_double_applying_anchor_day_events() -> None:
    baselines = [
        make_baseline(
            season="2023-24",
            player_id="player:incumbent",
            display_name="Incumbent",
            roster_order=1,
        ),
        make_baseline(
            season="2023-24",
            player_id="player:anchor-arrival",
            display_name="Anchor Arrival",
            roster_order=2,
        ),
        make_baseline(
            season="2023-24",
            player_id="player:next-anchor",
            display_name="Next Anchor",
            roster_order=3,
        ),
    ]
    source_events = [
        make_event(
            source_event_id="event:opening-signing",
            event_date="2023-10-01",
            event_type="signing",
            inbound=["Anchor Arrival"],
        ),
        make_event(
            source_event_id="event:midseason-signing",
            event_date="2023-10-03",
            event_type="signing",
            inbound=["Midseason Add"],
        ),
    ]
    aliases = [
        PlayerAliasRow(
            alias_id="alias:midseason-add",
            player_id="player:midseason-add",
            source_system="manual",
            alias_name="Midseason Add",
            normalized_alias_name="midseason add",
            is_manual=True,
        )
    ]
    snapshot_anchors = [
        daily_roster_state._RosterSnapshotAnchor(
            snapshot_id="snapshot:opening",
            snapshot_date=date(2023, 10, 1),
            snapshot_kind="season_opening",
            season="2023-24",
            team_code="MEM",
            source_record_id="snapshot-source:opening",
            players=[
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id="player:incumbent",
                    display_name="Incumbent",
                    depth_order=1,
                ),
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id="player:anchor-arrival",
                    display_name="Anchor Arrival",
                    depth_order=2,
                ),
            ],
        ),
        daily_roster_state._RosterSnapshotAnchor(
            snapshot_id="snapshot:deadline",
            snapshot_date=date(2024, 2, 15),
            snapshot_kind="post_deadline",
            season="2023-24",
            team_code="MEM",
            source_record_id="snapshot-source:deadline",
            players=[
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id="player:incumbent",
                    display_name="Incumbent",
                    depth_order=1,
                ),
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id="player:next-anchor",
                    display_name="Next Anchor",
                    depth_order=2,
                ),
            ],
        ),
    ]

    rows, player_rows = build_daily_roster_state_rows(
        baselines,
        source_events=source_events,
        player_aliases=aliases,
        snapshot_anchors=snapshot_anchors,
        fixture_path=None,
    )

    assert player_ids_for_date(player_rows, date(2023, 10, 1)) == [
        "player:incumbent",
        "player:anchor-arrival",
    ]
    assert row_for_date(rows, date(2023, 10, 1)).event_count == 1
    assert player_ids_for_date(player_rows, date(2023, 10, 3)) == [
        "player:incumbent",
        "player:anchor-arrival",
        "player:midseason-add",
    ]
    assert player_ids_for_date(player_rows, date(2024, 2, 15)) == [
        "player:incumbent",
        "player:next-anchor",
    ]


def test_build_daily_roster_state_limits_snapshot_interval_rows_to_graph_surface() -> None:
    baselines = [
        make_baseline(
            season="2023-24",
            player_id=f"player:hold-{index}",
            display_name=f"Hold {index}",
            roster_order=index,
        )
        for index in range(1, 19)
    ]
    baselines.extend(
        [
            make_baseline(
                season="2023-24",
                player_id="player:future-core",
                display_name="Future Core",
                roster_order=19,
            ),
            make_baseline(
                season="2023-24",
                player_id="player:transient",
                display_name="Transient",
                roster_order=20,
            ),
        ]
    )
    source_events = [
        make_event(
            source_event_id="event:future-core-signing",
            event_date="2024-03-01",
            event_type="signing",
            inbound=["Future Core"],
        ),
        make_event(
            source_event_id="event:transient-signing",
            event_date="2024-03-02",
            event_type="signing",
            inbound=["Transient"],
        ),
    ]
    snapshot_anchors = [
        daily_roster_state._RosterSnapshotAnchor(
            snapshot_id="snapshot:deadline",
            snapshot_date=date(2024, 2, 15),
            snapshot_kind="post_deadline",
            season="2023-24",
            team_code="MEM",
            source_record_id="snapshot-source:deadline",
            players=[
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id=f"player:hold-{index}",
                    display_name=f"Hold {index}",
                    depth_order=index,
                )
                for index in range(1, 19)
            ],
        ),
        daily_roster_state._RosterSnapshotAnchor(
            snapshot_id="snapshot:closing",
            snapshot_date=date(2024, 6, 30),
            snapshot_kind="season_closing",
            season="2023-24",
            team_code="MEM",
            source_record_id="snapshot-source:closing",
            players=[
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id=f"player:hold-{index}",
                    display_name=f"Hold {index}",
                    depth_order=index,
                )
                for index in range(1, 18)
            ]
            + [
                daily_roster_state._RosterSnapshotAnchorPlayer(
                    player_id="player:future-core",
                    display_name="Future Core",
                    depth_order=18,
                )
            ],
        ),
    ]

    rows, player_rows = build_daily_roster_state_rows(
        baselines,
        source_events=source_events,
        snapshot_anchors=snapshot_anchors,
        fixture_path=None,
    )

    march_2_players = player_ids_for_date(player_rows, date(2024, 3, 2))
    assert len(march_2_players) == 18
    assert "player:future-core" in march_2_players
    assert "player:transient" not in march_2_players
    assert row_for_date(rows, date(2024, 3, 2)).player_count == 18

from pathlib import Path


def test_draft_pick_resolution_bootstrap_sql_defines_guarded_resolution_table() -> None:
    sql_text = Path("sql/0005_foundation_draft_pick_resolution_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.draft_pick_resolution" in sql_text
    assert "references foundation.draft_selection" in sql_text
    assert "references foundation.pick" in sql_text
    assert "references foundation.asset" in sql_text
    assert "resolution_status in ('slot_verified')" in sql_text
    assert "draft_pick_resolution_selection_idx" in sql_text


def test_context_bootstrap_sql_defines_draft_lottery_result_contract() -> None:
    sql_text = Path("sql/0004_foundation_context_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.draft_lottery_result" in sql_text
    assert "lottery_result_id text primary key" in sql_text
    assert "draft_year integer not null" in sql_text
    assert "lottery_date date null" in sql_text
    assert "team_code text not null" in sql_text
    assert "lottery_position integer null" in sql_text
    assert "result_pick_slot integer not null" in sql_text
    assert "pre_lottery_odds text null" in sql_text
    assert "draft_lottery_result_year_team_idx" in sql_text
    assert "on foundation.draft_lottery_result (draft_year, team_code)" in sql_text

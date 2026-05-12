from pathlib import Path


def test_draft_pick_resolution_bootstrap_sql_defines_guarded_resolution_table() -> None:
    sql_text = Path("sql/0005_foundation_draft_pick_resolution_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.draft_pick_resolution" in sql_text
    assert "references foundation.draft_selection" in sql_text
    assert "references foundation.pick" in sql_text
    assert "references foundation.asset" in sql_text
    assert "resolution_status in ('slot_verified')" in sql_text
    assert "draft_pick_resolution_selection_idx" in sql_text

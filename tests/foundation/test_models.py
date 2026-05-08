from foundation.export import build_empty_base_export
from foundation.sources import get_default_source_plan


def test_empty_base_export_defaults() -> None:
    export = build_empty_base_export()
    assert export.franchise == "memphis-grizzlies"
    assert export.events == []
    assert export.transitions == []


def test_default_source_plan_includes_required_families() -> None:
    plan = get_default_source_plan()
    source_ids = {definition.source_id for definition in plan.source_definitions}
    assert source_ids == {
        "transactions_log",
        "player_reference",
        "pick_reference",
        "roster_state",
    }

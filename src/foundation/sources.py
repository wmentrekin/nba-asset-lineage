from __future__ import annotations

from pydantic import BaseModel, Field


class SourceDefinition(BaseModel):
    source_id: str
    purpose: str
    required_fields: list[str] = Field(default_factory=list)
    notes: str | None = None


class SourcePlan(BaseModel):
    franchise: str
    scope_start: str
    source_definitions: list[SourceDefinition] = Field(default_factory=list)


def get_default_source_plan() -> SourcePlan:
    return SourcePlan(
        franchise="memphis-grizzlies",
        scope_start="2016-07-01",
        source_definitions=[
            SourceDefinition(
                source_id="transactions_log",
                purpose="Complete Memphis transaction chronology for graph nodes.",
                required_fields=[
                    "event_date",
                    "event_type",
                    "transaction_label",
                    "inbound_assets",
                    "outbound_assets",
                ],
            ),
            SourceDefinition(
                source_id="player_reference",
                purpose="Stable player identity and display metadata.",
                required_fields=["player_id", "display_name"],
            ),
            SourceDefinition(
                source_id="pick_reference",
                purpose="Pick identity, ownership, protections, swaps, and resolution.",
                required_fields=["draft_year", "round_number", "original_team"],
            ),
            SourceDefinition(
                source_id="roster_state",
                purpose="Post-event roster validation and continuity checks.",
                required_fields=["as_of_date", "roster_asset_ids"],
            ),
        ],
    )

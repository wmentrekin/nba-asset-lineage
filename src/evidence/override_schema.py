from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class OverrideLinkSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    override_link_id: str | None = None
    source_record_id: str | None = None
    claim_id: str | None = None

    @field_validator("override_link_id", "source_record_id", "claim_id", mode="before")
    @classmethod
    def coerce_optional_string(cls, value: Any) -> str | None:
        return _string_or_none(value)


class OverrideEntrySchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    override_id: str | None = None
    override_type: str
    target_type: str
    target_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str
    authored_by: str | None = None
    authored_at: datetime | None = None
    is_active: bool = True
    links: list[OverrideLinkSchema] = Field(default_factory=list)

    @field_validator("override_id", "authored_by", mode="before")
    @classmethod
    def coerce_optional_string(cls, value: Any) -> str | None:
        return _string_or_none(value)

    @field_validator("override_type", "target_type", "target_key", "reason", mode="before")
    @classmethod
    def coerce_required_string(cls, value: Any) -> str:
        text = _string_or_none(value)
        if text is None:
            raise ValueError("must be a non-empty string")
        return text

    @field_validator("payload", mode="before")
    @classmethod
    def default_payload(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("must be an object")
        return value


class OverrideBundleSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    overrides: list[OverrideEntrySchema] = Field(default_factory=list)


def validate_override_bundle_payload(payload: dict[str, Any], *, source: str) -> OverrideBundleSchema:
    try:
        return OverrideBundleSchema.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid override bundle in {source}: {exc}") from exc

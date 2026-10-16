"""Typed data shared by ingestion, detectors, and the risk pipeline."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc(value: datetime) -> datetime:
    """Require an explicit timezone and store the value in UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


class GeoPoint(BaseModel):
    """A WGS84 point represented as latitude and longitude."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeoPolygon(BaseModel):
    """A minimal GeoJSON polygon with WGS84 ``[lon, lat]`` coordinates."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]

    @field_validator("coordinates")
    @classmethod
    def valid_coordinates(cls, value: list[list[list[float]]]) -> list[list[list[float]]]:
        if not value or not value[0] or len(value[0]) < 4:
            raise ValueError("a polygon needs a closed ring with at least four points")
        for point in value[0]:
            if len(point) != 2:
                raise ValueError("polygon points must be [lon, lat]")
            lon, lat = point
            if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                raise ValueError("polygon coordinates must be valid WGS84 values")
        if value[0][0] != value[0][-1]:
            raise ValueError("polygon ring must be closed")
        return value


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    detail: str | None = None


class Event(BaseModel):
    """Canonical event exchanged by ingestion and downstream modules."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    source_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    timestamp: datetime
    received_at: datetime
    geo: GeoPoint | GeoPolygon | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(default="1.0", min_length=1)
    raw_ref: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp", "received_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _utc(value)


class ModuleResult(BaseModel):
    """The fixed output shape for every detector."""

    model_config = ConfigDict(extra="forbid")

    module: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    label: str = Field(min_length=1)
    reasons: list[Reason]
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _utc(value)

from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, Request, UploadFile, File

from sentinal.chat import route as route_question
from sentinal.modules.satellite import analyze_change, rank_hotspots, analyze_rasters
from .errors import ApiError

router = APIRouter()
MAX_RASTER_BYTES = 50_000_000


def _array(payload: dict[str, Any], name: str) -> np.ndarray:
    value = payload.get(name)
    if value is None:
        raise ApiError("INVALID_SATELLITE_REQUEST", f"{name} is required")
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ApiError("INVALID_SATELLITE_REQUEST", f"{name} must be a numeric array") from exc
    if result.ndim != 2:
        raise ApiError("INVALID_SATELLITE_REQUEST", f"{name} must be a 2D numeric array")
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


@router.post("/satellite/change")
def change(request: Request, payload: dict[str, Any]):
    if payload.get("before_raster") is not None or payload.get("after_raster") is not None:
        if payload.get("before_raster") is None or payload.get("after_raster") is None:
            raise ApiError("INVALID_SATELLITE_REQUEST", "before_raster and after_raster are both required")
        result = analyze_rasters(payload["before_raster"], payload["after_raster"],
                                 before_band=int(payload.get("before_band", 1)), after_band=int(payload.get("after_band", 1)),
                                 threshold=float(payload.get("threshold", .15)), resampling=str(payload.get("resampling", "bilinear")))
        return _json_value(result)
    before = _array(payload, "before")
    after = _array(payload, "after")
    try:
        result = analyze_change(
            before,
            after,
            threshold=float(payload.get("threshold", 0.15)),
            cloud_cover=float(payload.get("cloud_cover", 0.0)),
            aoi=payload.get("aoi"),
        )
    except (TypeError, ValueError) as exc:
        raise ApiError("INVALID_SATELLITE_REQUEST", str(exc)) from exc

    if result["status"] == "ok":
        result["difference_mask"] = np.asarray(result["difference_mask"], dtype=bool)
        result["hotspots"] = rank_hotspots(
            result["difference_mask"],
            np.minimum(np.abs(after - before) / np.maximum(np.abs(before), 1e-9), 1.0),
        )
    result = _json_value(result)
    question = payload.get("question")
    if question is not None:
        result["chat"] = route_question(question, result)
    return result


@router.post("/satellite/change-upload")
async def change_upload(
    before_file: UploadFile = File(...),
    after_file: UploadFile = File(...),
    threshold: float = 0.15,
    resampling: str = "bilinear",
):
    """Process two uploaded GeoTIFFs without treating numeric arrays as imagery."""
    before = await before_file.read(MAX_RASTER_BYTES + 1)
    after = await after_file.read(MAX_RASTER_BYTES + 1)
    if len(before) > MAX_RASTER_BYTES or len(after) > MAX_RASTER_BYTES:
        raise ApiError("LIMIT_EXCEEDED", "each raster upload must be at most 50 MB")
    result = analyze_rasters(before, after, threshold=threshold, resampling=resampling)
    return _json_value(result)


def _filtered_events(request: Request, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    values = payload or {}
    events = [event for event in request.app.state.store.events if event.get("type") == "satellite"]
    for key in ("source_id", "scenario"):
        if values.get(key) is not None:
            events = [
                event
                for event in events
                if event.get(key) == values[key] or event.get("metadata", {}).get(key) == values[key]
            ]
    return events


def _page(items: list[dict[str, Any]], page: int, limit: int) -> dict[str, Any]:
    page = max(page, 1)
    limit = max(min(limit, 500), 1)
    start = (page - 1) * limit
    return {"items": items[start : start + limit], "page": page, "limit": limit, "total": len(items)}


@router.get("/satellite/query")
def query(request: Request, page: int = 1, limit: int = 50, source_id: str | None = None, scenario: str | None = None):
    return _page(_filtered_events(request, {"source_id": source_id, "scenario": scenario}), page, limit)


@router.post("/satellite/query")
def query_post(request: Request, payload: dict[str, Any]):
    page = int(payload.get("page", 1))
    limit = int(payload.get("limit", 50))
    return _page(_filtered_events(request, payload), page, limit)

"""GeoJSON export using only the standard library."""
from __future__ import annotations
import json
from typing import Any, Iterable, Mapping

def export_geojson(records: Iterable[Any], *, geometry_key: str = "geometry") -> bytes:
    features=[]
    for record in records:
        d = record.model_dump() if hasattr(record,"model_dump") else ({k:getattr(record,k) for k in record.__dataclass_fields__} if hasattr(record,"__dataclass_fields__") else dict(record))
        geometry=d.pop(geometry_key, None) or d.pop("geo", None)
        if hasattr(geometry,"model_dump"): geometry=geometry.model_dump()
        if geometry and geometry.get("type") == "GeoPoint": geometry={"type":"Point","coordinates":[geometry["lon"],geometry["lat"]]}
        elif geometry and "lat" in geometry and "lon" in geometry:
            geometry={"type":"Point","coordinates":[geometry["lon"],geometry["lat"]]}
        features.append({"type":"Feature","geometry":geometry,"properties":d})
    return json.dumps({"type":"FeatureCollection","features":features}, default=str, sort_keys=True).encode()

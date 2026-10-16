"""Offline CSV exports for risk results and explanation snapshots."""
from __future__ import annotations
import csv, io, json
from typing import Any, Iterable, Mapping

def _data(value: Any) -> Mapping[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return {k: getattr(value, k) for k in value.__dataclass_fields__}
    if hasattr(value, "model_dump"): return value.model_dump()
    if isinstance(value, Mapping): return value
    raise TypeError("expected a mapping, dataclass, or pydantic model")

def export_csv(records: Iterable[Any], *, fields: Iterable[str] | None = None) -> bytes:
    rows = [_data(r) for r in records]
    keys = list(fields or (rows[0].keys() if rows else []))
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, default=str, sort_keys=True) if isinstance(v,(dict,list,tuple)) else v for k,v in row.items()})
    return out.getvalue().encode("utf-8")

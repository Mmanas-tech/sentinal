"""Append-only, offline JSON-lines audit log."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json, os

def _safe(path: str | Path) -> Path:
    p=Path(path)
    if p.name in {"", ".", ".."} or any(part==".." for part in p.parts): raise ValueError("unsafe audit path")
    return p

def append_audit(path: str | Path, event: Mapping[str, Any]) -> None:
    p=_safe(path); p.parent.mkdir(parents=True, exist_ok=True)
    record={"timestamp":datetime.now(timezone.utc).isoformat(), **dict(event)}
    with p.open("a", encoding="utf-8") as f: f.write(json.dumps(record,default=str,sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())

def read_audit(path: str | Path) -> list[dict[str, Any]]:
    p=_safe(path)
    if not p.exists(): return []
    with p.open(encoding="utf-8") as f: return [json.loads(line) for line in f if line.strip()]

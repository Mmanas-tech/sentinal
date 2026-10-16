"""Deterministic timeline replay and what-if helpers."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

def _time(e: Mapping[str,Any]) -> datetime:
    value=e.get("timestamp") or e.get("time") or e.get("created_at")
    if isinstance(value,datetime): dt=value
    else: dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

class TimelineReplay:
    def __init__(self, events: Iterable[Mapping[str,Any]]):
        self.events=sorted((dict(e) for e in events), key=_time); self.cursor=0
    def page(self, limit: int=50) -> list[dict[str,Any]]:
        if limit<1: raise ValueError("limit must be positive")
        page=self.events[self.cursor:self.cursor+limit]; self.cursor+=len(page); return page
    def reset(self) -> None: self.cursor=0
    def replay(self, callback: Callable[[dict[str,Any]],Any] | None=None) -> list[Any]:
        self.reset(); out=[]
        while True:
            page=self.page()
            if not page: return out
            if callback:
                out.extend(callback(e) for e in page)
            else:
                out.extend(page)

def what_if(events: Iterable[Mapping[str,Any]], adapter: Callable[[dict[str,Any]],Any], *, override: Mapping[str,Any] | None=None) -> list[Any]:
    return [adapter({**dict(event), **(override or {})}) for event in sorted(events,key=_time)]

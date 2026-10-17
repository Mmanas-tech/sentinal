"""Boundaries that turn local/remote records into validated canonical Events.

The generic HTTP contract is deliberately provider-neutral: a GET returns either
an array of event objects or ``{"events": [...]}``; streaming endpoints return
one JSON event per line.  Adapters never claim LIVE until a request succeeds.
"""
from __future__ import annotations

import csv, json, os, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError
from sentinal.core.schemas import Event

STATUSES = {"LIVE", "FILE-BASED", "DEMO", "DEGRADED", "OFFLINE"}

@dataclass
class AdapterError:
    location: str
    message: str
    code: str = "INVALID"

@dataclass
class AdapterResult:
    events: list[Event] = field(default_factory=list)
    errors: list[AdapterError] = field(default_factory=list)
    source_id: str = ""
    status: str = "OFFLINE"
    provenance: str = ""

class IngestionAdapter:
    source_id = "unknown"
    status = "OFFLINE"
    provenance = ""

    def _events(self, records: Iterable[Any], provenance: str, status: str) -> AdapterResult:
        result = AdapterResult(source_id=self.source_id, status=status, provenance=provenance)
        seen: set[tuple[str, str]] = set()
        for location, raw in records:
            try:
                if not isinstance(raw, dict): raise ValueError("record must be an object")
                item = dict(raw)
                for field_name in ("payload", "geo", "metadata"):
                    value = item.get(field_name)
                    if isinstance(value, str) and value.strip():
                        try:
                            item[field_name] = json.loads(value)
                        except json.JSONDecodeError as exc:
                            raise ValueError(f"{field_name} must contain valid JSON") from exc
                item.setdefault("received_at", datetime.now(timezone.utc).isoformat())
                item.setdefault("raw_ref", f"{provenance}#{location}")
                item.setdefault("metadata", {})
                item["metadata"] = {**item["metadata"], "source_status": status, "provenance": provenance}
                event = Event.model_validate(item)
                key = (event.source_id, event.id)
                if key in seen:
                    result.errors.append(AdapterError(str(location), "duplicate event", "DUPLICATE")); continue
                seen.add(key); result.events.append(event)
            except (ValidationError, ValueError, TypeError) as exc:
                result.errors.append(AdapterError(str(location), str(exc)))
        return result

class FileAdapter(IngestionAdapter):
    def __init__(self, source_id: str, max_bytes: int = 10_000_000, max_records: int = 5000):
        self.source_id, self.max_bytes, self.max_records = source_id, max_bytes, max_records

class CSVAdapter(FileAdapter):
    def read(self, path: str | Path) -> AdapterResult:
        path = Path(path); provenance = str(path.resolve())
        if path.suffix.lower() != ".csv": return AdapterResult(source_id=self.source_id, provenance=provenance, errors=[AdapterError("file", "unsupported format; expected .csv", "UNSUPPORTED_FORMAT")])
        try:
            if path.stat().st_size > self.max_bytes: raise ValueError("file exceeds size limit")
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = csv.DictReader(handle)
                if not rows.fieldnames: raise ValueError("CSV requires a header row")
                records = list(rows)
            if len(records) > self.max_records: raise ValueError("record count exceeds limit")
            return self._events(((i + 2, row) for i, row in enumerate(records)), provenance, "FILE-BASED")
        except Exception as exc: return AdapterResult(source_id=self.source_id, provenance=provenance, errors=[AdapterError("file", str(exc), "FILE_ERROR")])

class JSONLAdapter(FileAdapter):
    def read(self, path: str | Path) -> AdapterResult:
        path = Path(path); provenance = str(path.resolve())
        if path.suffix.lower() not in {".jsonl", ".ndjson"}: return AdapterResult(source_id=self.source_id, provenance=provenance, errors=[AdapterError("file", "unsupported format; expected .jsonl or .ndjson", "UNSUPPORTED_FORMAT")])
        try:
            if path.stat().st_size > self.max_bytes: raise ValueError("file exceeds size limit")
            records = []
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    if not line.strip(): continue
                    if len(records) >= self.max_records: raise ValueError("record count exceeds limit")
                    try: records.append((line_no, json.loads(line)))
                    except json.JSONDecodeError as exc: records.append((line_no, {"__parse_error__": str(exc)}))
            result = self._events(((n, r) for n, r in records), provenance, "FILE-BASED")
            parse_lines = {str(n) for n, raw in records if isinstance(raw, dict) and "__parse_error__" in raw}
            for error in result.errors:
                if error.location in parse_lines: error.code = "INVALID_JSON"
            return result
        except Exception as exc: return AdapterResult(source_id=self.source_id, provenance=provenance, errors=[AdapterError("file", str(exc), "FILE_ERROR")])

class HTTPAdapter(IngestionAdapter):
    def __init__(self, source_id: str | None = None, url: str | None = None, token: str | None = None, timeout: float | None = None, retries: int | None = None, backoff: float | None = None):
        self.source_id = source_id or os.getenv("SENTINAL_HTTP_SOURCE_ID", "external-http")
        self.url = url or os.getenv("SENTINAL_HTTP_URL")
        self.token = token if token is not None else os.getenv("SENTINAL_HTTP_TOKEN")
        self.timeout = timeout or float(os.getenv("SENTINAL_HTTP_TIMEOUT", "10")); self.retries = retries if retries is not None else int(os.getenv("SENTINAL_HTTP_RETRIES", "2")); self.backoff = backoff or float(os.getenv("SENTINAL_HTTP_BACKOFF", "0.5"))
    def fetch(self) -> AdapterResult:
        if not self.url: return AdapterResult(source_id=self.source_id, errors=[AdapterError("config", "SENTINAL_HTTP_URL is required", "NOT_CONFIGURED")])
        for attempt in range(self.retries + 1):
            try:
                headers = {"Accept": "application/json"};
                if self.token: headers["Authorization"] = f"Bearer {self.token}"
                with urlopen(Request(self.url, headers=headers), timeout=self.timeout) as response: payload = json.loads(response.read(self.max_bytes if hasattr(self, 'max_bytes') else 10_000_000))
                records = payload.get("events", payload) if isinstance(payload, dict) else payload
                return self._events(((i + 1, r) for i, r in enumerate(records)), self.url, "LIVE")
            except HTTPError as exc:
                if exc.code in (401, 403): return AdapterResult(source_id=self.source_id, errors=[AdapterError("request", f"authentication failed ({exc.code})", "AUTH_ERROR")])
                last = f"HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc: last = str(exc)
            if attempt < self.retries: time.sleep(self.backoff * (2 ** attempt))
        return AdapterResult(source_id=self.source_id, status="DEGRADED", errors=[AdapterError("request", last, "REQUEST_ERROR")])

class HTTPStreamAdapter(HTTPAdapter):
    async def stream(self) -> AsyncIterator[Event]:
        """Consume newline-delimited JSON; yields only validated events."""
        if not self.url: raise ValueError("SENTINAL_HTTP_URL is required")
        try:
            import httpx
        except ImportError as exc: raise RuntimeError("install httpx for HTTP streaming") from exc
        headers = {"Accept": "application/x-ndjson"};
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("GET", self.url, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line: yield Event.model_validate(json.loads(line))


class OpenMeteoAdapter(HTTPAdapter):
    """Fetch real weather observations from the documented Open-Meteo API.

    Open-Meteo exposes a public forecast endpoint and does not require an API
    key for the normal public service. The adapter still reports ``OFFLINE``
    or ``DEGRADED`` when the request cannot be completed; it never substitutes
    a synthetic weather value.
    """

    endpoint = "https://api.open-meteo.com/v1/forecast"

    def __init__(
        self,
        source_id: str = "open-meteo",
        *,
        timeout: float = 10.0,
        retries: int = 2,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(source_id=source_id, url=endpoint or self.endpoint, timeout=timeout, retries=retries)

    def fetch(self) -> AdapterResult:  # type: ignore[override]
        """Fetch the configured URL; ``fetch_location`` is the public location API."""
        if not self.url:
            return AdapterResult(source_id=self.source_id, errors=[AdapterError("config", "endpoint is required", "NOT_CONFIGURED")])
        for attempt in range(self.retries + 1):
            try:
                with urlopen(Request(self.url, headers={"Accept": "application/json"}), timeout=self.timeout) as response:
                    payload = json.loads(response.read(10_000_000))
                hourly = payload.get("hourly")
                if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
                    return AdapterResult(source_id=self.source_id, status="DEGRADED", errors=[AdapterError("response", "Open-Meteo response has no hourly time series", "INVALID_RESPONSE")])
                records = []
                for index, timestamp in enumerate(hourly["time"]):
                    temperature = (hourly.get("temperature_2m") or [None] * len(hourly["time"]))[index]
                    precipitation = (hourly.get("precipitation") or [None] * len(hourly["time"]))[index]
                    wind = (hourly.get("wind_speed_10m") or [None] * len(hourly["time"]))[index]
                    payload_record = {
                        "id": f"{self.source_id}:{timestamp}",
                        "source_id": self.source_id,
                        "type": "environment",
                        "timestamp": str(timestamp) if "+" in str(timestamp) or str(timestamp).endswith("Z") else f"{timestamp}:00+00:00" if len(str(timestamp)) == 13 else f"{timestamp}+00:00",
                        "geo": {"lat": float(payload.get("latitude", 0)), "lon": float(payload.get("longitude", 0))},
                        "payload": {"temperature_c": temperature, "rainfall_mm": precipitation, "wind_speed_mps": wind},
                        "metadata": {"source_status": "LIVE", "provider": "Open-Meteo", "provider_response": payload.get("generationtime_ms")},
                    }
                    records.append((index, payload_record))
                return self._events(records, self.url, "LIVE")
            except HTTPError as exc:
                if exc.code in (401, 403):
                    return AdapterResult(source_id=self.source_id, status="DEGRADED", errors=[AdapterError("request", f"Open-Meteo authentication failed ({exc.code})", "AUTH_ERROR")])
                last = f"HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
                last = str(exc)
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))
        return AdapterResult(source_id=self.source_id, status="DEGRADED", errors=[AdapterError("request", last, "REQUEST_ERROR")])

    def fetch_location(self, latitude: float, longitude: float, *, forecast_hours: int = 1) -> AdapterResult:
        """Fetch a location and normalize hourly weather observations to Events."""
        if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
            return AdapterResult(source_id=self.source_id, status="DEGRADED", errors=[AdapterError("coordinates", "latitude/longitude are outside WGS84 bounds", "INVALID_COORDINATES")])
        if forecast_hours < 1 or forecast_hours > 168:
            return AdapterResult(source_id=self.source_id, status="DEGRADED", errors=[AdapterError("forecast_hours", "forecast_hours must be between 1 and 168", "INVALID_PARAMETER")])
        self.url = f"{self.endpoint}?{urlencode({'latitude': latitude, 'longitude': longitude, 'hourly': 'temperature_2m,precipitation,wind_speed_10m', 'forecast_hours': forecast_hours, 'wind_speed_unit': 'ms', 'timezone': 'UTC'})}"
        return self.fetch()

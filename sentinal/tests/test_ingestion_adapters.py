import io
import json
from datetime import datetime, timezone
from urllib.error import URLError

import pytest

from sentinal.ingestion import CSVAdapter, HTTPAdapter, JSONLAdapter, OpenMeteoAdapter


def event_record(event_id: str = "evt-1") -> dict:
    return {
        "id": event_id,
        "source_id": "fixture-source",
        "type": "environment",
        "timestamp": "2026-01-01T00:00:00Z",
        "received_at": "2026-01-01T00:00:01Z",
        "raw_ref": f"fixture://{event_id}",
        "payload": {"rainfall_mm": 10},
    }


def test_csv_adapter_normalizes_valid_rows_and_reports_invalid_rows(tmp_path) -> None:
    path = tmp_path / "events.csv"
    path.write_text(
        "id,source_id,type,timestamp,received_at,raw_ref,payload\n"
        f"evt-1,source-a,environment,2026-01-01T00:00:00Z,2026-01-01T00:00:01Z,fixture://1,{json.dumps({'rainfall_mm': 2})}\n"
        "bad,source-b,not-a-type,not-a-time,,fixture://bad,{}\n",
        encoding="utf-8",
    )

    result = CSVAdapter("csv-upload").read(path)

    assert result.status == "FILE-BASED"
    assert len(result.events) == 1
    assert result.events[0].metadata["source_status"] == "FILE-BASED"
    assert result.errors


def test_jsonl_adapter_reports_parse_errors_and_duplicates(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    first = event_record("evt-1")
    path.write_text(
        json.dumps(first) + "\n"
        "not-json\n"
        + json.dumps(first)
        + "\n",
        encoding="utf-8",
    )

    result = JSONLAdapter("jsonl-upload").read(path)

    assert len(result.events) == 1
    assert {error.code for error in result.errors} >= {"INVALID_JSON", "DUPLICATE"}


def test_http_adapter_missing_configuration_is_explicit() -> None:
    result = HTTPAdapter(source_id="external-test", url=None).fetch()

    assert result.status == "OFFLINE"
    assert result.errors[0].code == "NOT_CONFIGURED"


def test_http_adapter_retries_and_reports_degraded(monkeypatch) -> None:
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise URLError("fixture timeout")

    monkeypatch.setattr("sentinal.ingestion.adapters.urlopen", fail)
    result = HTTPAdapter(url="https://example.invalid", retries=2, backoff=0).fetch()

    assert len(calls) == 3
    assert result.status == "DEGRADED"
    assert result.errors[0].code == "REQUEST_ERROR"


def test_open_meteo_adapter_normalizes_documented_response(monkeypatch) -> None:
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    payload = {
        "latitude": 51.05,
        "longitude": 13.74,
        "hourly": {
            "time": ["2026-01-01T00:00"],
            "temperature_2m": [4.0],
            "precipitation": [1.5],
            "wind_speed_10m": [5.0],
        },
    }
    monkeypatch.setattr(
        "sentinal.ingestion.adapters.urlopen",
        lambda *args, **kwargs: Response(json.dumps(payload).encode("utf-8")),
    )

    result = OpenMeteoAdapter(endpoint="https://fixture.open-meteo.test").fetch_location(51.05, 13.74)

    assert result.status == "LIVE"
    assert len(result.events) == 1
    assert result.events[0].type == "environment"
    assert result.events[0].payload["rainfall_mm"] == 1.5
    assert result.events[0].metadata["provider"] == "Open-Meteo"


def test_open_meteo_rejects_invalid_location() -> None:
    result = OpenMeteoAdapter(endpoint="https://fixture.open-meteo.test").fetch_location(100, 0)

    assert result.status == "DEGRADED"
    assert result.errors[0].code == "INVALID_COORDINATES"

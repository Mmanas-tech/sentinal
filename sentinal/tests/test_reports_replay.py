from datetime import datetime, timezone

import pytest

from sentinal.alerts.audit import append_audit, read_audit
from sentinal.alerts.replay import TimelineReplay, what_if
from sentinal.reports.csv_export import export_csv
from sentinal.reports.geojson_export import export_geojson
from sentinal.reports.pdf_report import generate_pdf


def test_csv_geojson_and_pdf_exports(tmp_path) -> None:
    records = [{"id": "a", "score": 72, "geo": {"lat": 1, "lon": 2}}]

    csv_data = export_csv(records)
    geojson = export_geojson(records)
    assert b"id,score" in csv_data
    assert b"FeatureCollection" in geojson
    assert b'"coordinates": [2, 1]' in geojson

    try:
        pdf = generate_pdf(records)
    except RuntimeError as exc:
        assert "reportlab" in str(exc)
    else:
        assert pdf.startswith(b"%PDF")


def test_audit_is_append_only_and_safe(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit(path, {"action": "view", "target": "alert-1"})
    append_audit(path, {"action": "acknowledge", "target": "alert-1"})

    records = read_audit(path)
    assert len(records) == 2
    assert records[0]["action"] == "view"
    with pytest.raises(ValueError, match="unsafe"):
        append_audit(tmp_path / ".." / "unsafe.jsonl", {})


def test_replay_sorts_utc_and_pages() -> None:
    events = [
        {"id": "late", "timestamp": "2026-01-01T00:02:00Z"},
        {"id": "first", "timestamp": "2026-01-01T00:01:00+00:00"},
    ]
    replay = TimelineReplay(events)

    assert [event["id"] for event in replay.page(1)] == ["first"]
    assert [event["id"] for event in replay.page(1)] == ["late"]
    assert replay.page(1) == []
    assert [event["id"] for event in replay.replay()] == ["first", "late"]


def test_replay_what_if_applies_non_destructive_override() -> None:
    events = [{"timestamp": "2026-01-01T00:00:00Z", "value": 1}]
    result = what_if(events, lambda event: event["value"], override={"value": 9})

    assert result == [9]
    assert events[0]["value"] == 1

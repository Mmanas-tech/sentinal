import asyncio
from datetime import datetime, timezone

import pytest

from sentinal.core.config_loader import ConfigError, load_config
from sentinal.core.contract import ModuleContractError, validate_module_result
from sentinal.core.event_bus import EventBus
from sentinal.core.schemas import Event


def make_event(event_id: str = "evt_1", source_id: str = "source_1") -> Event:
    timestamp = datetime.fromisoformat("2026-01-01T12:00:00+02:00")
    return Event(
        id=event_id,
        source_id=source_id,
        type="telemetry",
        timestamp=timestamp,
        received_at=datetime.now(timezone.utc),
        raw_ref=f"raw/{event_id}",
        geo={"lat": 51.05, "lon": 13.74},
        payload={"seq": 1},
    )


def test_event_round_trip_normalizes_timestamps_and_geo() -> None:
    event = make_event()
    restored = Event.model_validate_json(event.model_dump_json())

    assert restored.timestamp == datetime.fromisoformat("2026-01-01T10:00:00+00:00")
    assert restored.timestamp.tzinfo == timezone.utc
    assert restored.geo is not None
    assert restored.geo.lat == 51.05


def test_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Event(
            source_id="source_1",
            type="telemetry",
            timestamp=datetime(2026, 1, 1, 12, 0),
            received_at=datetime.now(timezone.utc),
            raw_ref="raw/naive",
        )


def test_module_contract_requires_a_reason() -> None:
    result = {
        "module": "telemetry_validator",
        "signal_id": "sig_1",
        "score": 0.8,
        "label": "abnormal_value",
        "reasons": [],
        "evidence": [],
        "confidence": 0.9,
        "timestamp": "2026-01-01T12:00:00Z",
    }

    with pytest.raises(ModuleContractError, match="at least one reason"):
        validate_module_result(result)


def test_module_contract_accepts_structured_result() -> None:
    result = validate_module_result(
        {
            "module": "telemetry_validator",
            "signal_id": "sig_1",
            "score": 0.8,
            "label": "abnormal_value",
            "reasons": [{"code": "OUT_OF_RANGE", "detail": "battery_v=55"}],
            "evidence": [{"type": "packet", "ref": "pkt_1"}],
            "confidence": 0.9,
            "timestamp": "2026-01-01T12:00:00Z",
        }
    )

    assert result.score == 0.8
    assert result.timestamp.tzinfo == timezone.utc


def test_event_bus_deduplicates_by_source_and_event_id() -> None:
    async def scenario() -> list[str]:
        seen: list[str] = []
        bus = EventBus()
        bus.subscribe("telemetry", lambda event: seen.append(event.source_id))

        assert await bus.publish(make_event(event_id="evt_same", source_id="source_a"))
        assert not await bus.publish(make_event(event_id="evt_same", source_id="source_a"))
        assert await bus.publish(make_event(event_id="evt_same", source_id="source_b"))
        return seen

    assert asyncio.run(scenario()) == ["source_a", "source_b"]


def test_default_config_bundle_loads_and_validates_weights() -> None:
    bundle = load_config()

    assert {"schemas", "weights", "thresholds", "playbooks", "assets"} <= bundle.keys()
    assert sum(bundle["weights"]["factors"].values()) == pytest.approx(1.0)


def test_config_loader_rejects_invalid_weight_sum(tmp_path) -> None:
    path = tmp_path / "weights.yaml"
    path.write_text("factors: {satellite: 0.4, telemetry: 0.4}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="sum"):
        load_config(path)

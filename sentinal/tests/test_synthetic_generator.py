from datetime import timezone

import pytest

from sentinal.ingestion import SyntheticGenerator
from sentinal.ingestion.synthetic_generator import ANOMALIES


SCENARIO_EVENT_TYPES = {
    "flood": "environment",
    "wildfire": "environment",
    "satellite_fault": "satellite",
    "cyber_attack": "cyber",
}


def test_each_scenario_emits_telemetry_and_its_side_channel() -> None:
    generator = SyntheticGenerator()

    for scenario, side_channel in SCENARIO_EVENT_TYPES.items():
        result = generator.generate(scenario, count=8, seed=11)
        types = [event.type for event in result.events]

        assert types.count("telemetry") == 8
        assert types.count(side_channel) == 8
        assert all(event.timestamp.tzinfo == timezone.utc for event in result.events)
        assert all(event.raw_ref for event in result.events)
        assert len({event.id for event in result.events}) == len(result.events)


def test_generation_is_reproducible_but_clean_telemetry_varies() -> None:
    generator = SyntheticGenerator()
    first = generator.generate("wildfire", count=10, seed=4)
    second = generator.generate("wildfire", count=10, seed=4)

    assert first.model_dump() == second.model_dump()
    telemetry = [event for event in first.events if event.type == "telemetry"]
    assert len({event.payload["battery_v"] for event in telemetry}) > 1


def test_all_seven_faults_are_planted_and_marked() -> None:
    result = SyntheticGenerator().generate(
        "flood",
        count=14,
        seed=3,
        plant_anomalies=["all"],
    )
    telemetry = {event.id: event for event in result.events if event.type == "telemetry"}

    assert {item["type"] for item in result.planted_anomalies} == set(ANOMALIES)
    for item in result.planted_anomalies:
        event = telemetry[item["event_id"]]
        assert item["type"] in event.metadata["planted_faults"]

    missing = next(event for event in telemetry.values() if "missing_field" in event.metadata["planted_faults"])
    assert "temp_c" not in missing.payload

    out_of_range = next(event for event in telemetry.values() if "out_of_range" in event.metadata["planted_faults"])
    assert out_of_range.payload["battery_v"] == 999.0

    wrong_type = next(event for event in telemetry.values() if "wrong_type" in event.metadata["planted_faults"])
    assert isinstance(wrong_type.payload["temp_c"], str)

    stale = next(event for event in telemetry.values() if "stale_data" in event.metadata["planted_faults"])
    assert (stale.received_at - stale.timestamp).total_seconds() > 60


def test_explicit_fault_selection_and_parameter_validation() -> None:
    generator = SyntheticGenerator()
    result = generator.generate("cyber_attack", count=3, seed=1, plant_anomalies=["sudden_jump"])

    assert [item["type"] for item in result.planted_anomalies] == ["sudden_jump"]
    assert len([event for event in result.events if event.type == "telemetry"]) == 3

    with pytest.raises(ValueError, match="unknown scenario"):
        generator.generate("unknown", count=3)
    with pytest.raises(ValueError, match="unknown anomaly"):
        generator.generate("flood", count=3, plant_anomalies=["not_a_fault"])
    with pytest.raises(ValueError, match="at least the number"):
        generator.generate("flood", count=1, plant_anomalies=["missing_field", "stale_data"])


def test_clean_run_does_not_require_seven_samples() -> None:
    result = SyntheticGenerator().generate("satellite_fault", count=1, seed=5)

    assert len(result.events) == 2
    assert result.planted_anomalies == []

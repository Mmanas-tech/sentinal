from datetime import datetime, timedelta, timezone

import pytest

from sentinal.core.schemas import Event
from sentinal.ingestion import SyntheticGenerator
from sentinal.modules.telemetry import (
    CommandValidator,
    HealthTracker,
    IsolationForestDetector,
    RollingZScoreDetector,
    TelemetryValidator,
)


BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def packet(
    *,
    seq: int = 0,
    timestamp: datetime = BASE_TIME,
    received_at: datetime | None = None,
    session_id: str = "session-1",
    **updates,
) -> dict:
    value = {
        "source_id": "sensor-1",
        "received_at": received_at or timestamp + timedelta(seconds=1),
        "seq": seq,
        "timestamp": timestamp,
        "session_id": session_id,
        "battery_v": 12.0,
        "temp_c": 25.0,
        "solar_current_a": 4.0,
        "lat": 51.05,
        "lon": 13.74,
    }
    value.update(updates)
    return value


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_valid_packet_is_ok_and_zero_is_not_missing() -> None:
    validator = TelemetryValidator()

    result = validator.validate(packet(battery_v=0.0))

    assert result.level == "OK"
    assert result.valid
    assert "MISSING_FIELD" not in codes(result)


def test_missing_and_null_fields_are_distinct_and_quarantined() -> None:
    missing = packet()
    missing.pop("temp_c")
    null = packet(temp_c=None)

    missing_result = TelemetryValidator().validate(missing)
    null_result = TelemetryValidator().validate(null)

    assert "MISSING_FIELD" in codes(missing_result)
    assert "NULL_FIELD" in codes(null_result)
    assert missing_result.quarantined and null_result.quarantined


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"battery_v": 999.0}, "OUT_OF_RANGE"),
        ({"temp_c": "not-a-number"}, "WRONG_TYPE"),
        ({"units": {"battery_v": "mV"}}, "UNIT_MISMATCH"),
    ],
)
def test_value_type_and_unit_rules(updates: dict, expected: str) -> None:
    result = TelemetryValidator().validate(packet(**updates))

    assert expected in codes(result)
    assert result.quarantined


def test_unknown_field_is_reported_without_quarantine() -> None:
    result = TelemetryValidator().validate(packet(new_sensor_value=3.0))

    assert "UNKNOWN_FIELD" in codes(result)
    assert result.level == "WARN"
    assert result.valid
    assert not result.quarantined


def test_stale_late_and_clock_drift_rules() -> None:
    validator = TelemetryValidator()

    late = validator.validate(
        packet(
            timestamp=BASE_TIME,
            received_at=BASE_TIME + timedelta(seconds=40),
        )
    )
    stale = TelemetryValidator().validate(
        packet(
            timestamp=BASE_TIME,
            received_at=BASE_TIME + timedelta(seconds=61),
        )
    )
    future = TelemetryValidator().validate(
        packet(
            timestamp=BASE_TIME + timedelta(seconds=20),
            received_at=BASE_TIME,
        )
    )

    assert "LATE_DATA" in codes(late)
    assert "LATE" in late.tags
    assert "STALE_DATA" in codes(stale)
    assert "CLOCK_DRIFT" in codes(future)


def test_sequence_duplicate_gap_out_of_order_and_rollover() -> None:
    duplicate_validator = TelemetryValidator()
    duplicate_validator.validate(packet(seq=4))
    duplicate = duplicate_validator.validate(packet(seq=4, timestamp=BASE_TIME + timedelta(seconds=1)))

    gap_validator = TelemetryValidator()
    gap_validator.validate(packet(seq=0))
    gap = gap_validator.validate(packet(seq=3, timestamp=BASE_TIME + timedelta(seconds=1)))
    out_of_order = gap_validator.validate(packet(seq=2, timestamp=BASE_TIME + timedelta(seconds=2)))

    rollover_validator = TelemetryValidator()
    rollover_validator.validate(packet(seq=65535))
    rollover = rollover_validator.validate(packet(seq=0, timestamp=BASE_TIME + timedelta(seconds=1)))

    assert "DUPLICATE_SEQUENCE" in codes(duplicate)
    assert "SEQUENCE_GAP" in codes(gap)
    assert "OUT_OF_ORDER" in codes(out_of_order)
    assert "LATE" in out_of_order.tags
    assert rollover.level == "OK"


def test_session_and_boot_resets_do_not_create_sequence_findings() -> None:
    validator = TelemetryValidator()
    validator.validate(packet(seq=10))
    session_reset = validator.validate(packet(seq=0, session_id="session-2"))
    boot_reset = validator.validate(packet(seq=0, session_id="session-2", boot=True))

    assert "DUPLICATE_SEQUENCE" not in codes(session_reset)
    assert "SEQUENCE_GAP" not in codes(session_reset)
    assert "SESSION_RESET" in session_reset.tags
    assert "SESSION_RESET" in boot_reset.tags


def test_sudden_jump_and_burst_incident_grouping() -> None:
    validator = TelemetryValidator()
    validator.validate(packet(seq=0, temp_c=20.0))
    jump = validator.validate(packet(seq=1, temp_c=60.0, timestamp=BASE_TIME + timedelta(seconds=1)))

    first_bad = validator.validate(packet(seq=2, battery_v=999.0, timestamp=BASE_TIME + timedelta(seconds=2)))
    second_bad = validator.validate(packet(seq=3, battery_v=999.0, timestamp=BASE_TIME + timedelta(seconds=3)))
    later_bad = validator.validate(
        packet(
            seq=4,
            battery_v=999.0,
            timestamp=BASE_TIME + timedelta(seconds=100),
            received_at=BASE_TIME + timedelta(seconds=100),
        )
    )

    assert "SUDDEN_JUMP" in codes(jump)
    assert first_bad.incident_group == second_bad.incident_group
    assert later_bad.incident_group != first_bad.incident_group


def test_malformed_json_is_safe_and_quarantined() -> None:
    validator = TelemetryValidator()

    invalid = validator.validate_raw("{not json")
    array = validator.validate_raw("[1, 2, 3]")

    assert invalid.level == "CRITICAL"
    assert "MALFORMED_JSON" in codes(invalid)
    assert array.quarantined
    assert len(validator.quarantine) == 2


def test_event_input_uses_canonical_received_at() -> None:
    event = Event(
        id="evt_telemetry_test",
        source_id="sensor-1",
        type="telemetry",
        timestamp=BASE_TIME,
        received_at=BASE_TIME + timedelta(seconds=1),
        raw_ref="test://packet",
        payload=packet(seq=0),
    )

    result = TelemetryValidator().validate(event)

    assert result.level == "OK"


def test_rolling_z_score_and_optional_isolation_forest() -> None:
    zscore = RollingZScoreDetector(window=5, threshold=3.0, min_samples=3)
    for _ in range(3):
        zscore.update(10.0, source="s", sensor="temp_c")
    anomaly = zscore.update(100.0, source="s", sensor="temp_c")
    disabled = IsolationForestDetector(enabled=False).update(100.0)

    assert anomaly["anomalous"]
    assert anomaly["z_score"] > 3.0
    assert disabled["disabled"]
    assert not disabled["anomalous"]


def test_validator_emits_rolling_statistical_anomaly() -> None:
    validator = TelemetryValidator()
    for sequence in range(3):
        validator.validate(packet(seq=sequence, temp_c=25.0, timestamp=BASE_TIME + timedelta(seconds=sequence)))

    result = validator.validate(packet(seq=3, temp_c=40.0, timestamp=BASE_TIME + timedelta(seconds=3)))

    assert "STATISTICAL_ANOMALY" in codes(result)


def test_command_validator_checks_auth_params_sequence_and_replay() -> None:
    validator = CommandValidator()
    valid = validator.validate(
        {
            "command_id": "SET_MODE",
            "sender": "mission_controller",
            "session_id": "cmd-session",
            "seq": 0,
            "nonce": "nonce-1",
            "parameters": {"mode": "nominal"},
        }
    )
    replay = validator.validate(
        {
            "command_id": "SET_MODE",
            "sender": "mission_controller",
            "session_id": "cmd-session",
            "seq": 0,
            "nonce": "nonce-1",
            "parameters": {"mode": "nominal"},
        }
    )
    invalid = validator.validate(
        {
            "command_id": "SET_TARGET",
            "sender": "intruder",
            "session_id": "cmd-session",
            "seq": 1,
            "nonce": "nonce-2",
            "parameters": {"latitude": 100, "longitude": "west", "extra": True},
        }
    )

    assert valid.level == "OK"
    assert "REPLAY" in codes(replay)
    assert {"SENDER_NOT_ALLOWED", "OUT_OF_RANGE", "WRONG_TYPE", "UNKNOWN_PARAMETER"} <= codes(invalid)


def test_health_tracker_reports_scores_loss_and_latency() -> None:
    tracker = HealthTracker()
    healthy = tracker.record_packet(
        "sensor-1",
        latency_s=1.0,
        packet={"battery_v": 12.0, "solar_current_a": 4.0, "temp_c": 25.0},
    )
    degraded = tracker.record_packet("sensor-1", latency_s=20.0, lost=True)

    assert healthy["packet_loss_pct"] == 0
    assert healthy["subsystems"]["power"] > 0
    assert healthy["subsystems"]["thermal"] == 100
    assert degraded["packet_loss_pct"] == 50
    assert degraded["subsystems"]["comms"] == 0


def test_validator_catches_all_generator_planted_faults() -> None:
    result = SyntheticGenerator().generate("flood", count=14, seed=42, plant_anomalies=["all"])
    validator = TelemetryValidator()
    outcomes = {}

    for event in result.events:
        if event.type != "telemetry":
            continue
        outcome = validator.validate(event)
        for fault in event.metadata["planted_faults"]:
            outcomes[fault] = codes(outcome)

    assert "MISSING_FIELD" in outcomes["missing_field"]
    assert "OUT_OF_RANGE" in outcomes["out_of_range"]
    assert "WRONG_TYPE" in outcomes["wrong_type"]
    assert "DUPLICATE_SEQUENCE" in outcomes["duplicate_sequence"]
    assert {"SEQUENCE_GAP", "OUT_OF_ORDER"} & outcomes["gap_out_of_order"]
    assert "STALE_DATA" in outcomes["stale_data"]
    assert "SUDDEN_JUMP" in outcomes["sudden_jump"]

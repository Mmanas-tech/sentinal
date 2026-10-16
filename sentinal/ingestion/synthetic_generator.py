"""Deterministic synthetic canonical events for SENTINAL demo scenarios."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sentinal.core.config_loader import DEFAULT_CONFIG_DIR, load_config
from sentinal.core.schemas import Event, GeoPoint


ANOMALIES: tuple[str, ...] = (
    "missing_field",
    "out_of_range",
    "wrong_type",
    "duplicate_sequence",
    "gap_out_of_order",
    "stale_data",
    "sudden_jump",
)
SCENARIOS: tuple[str, ...] = (
    "flood",
    "wildfire",
    "satellite_fault",
    "cyber_attack",
)


class SyntheticResult(BaseModel):
    """A reproducible synthetic run and the faults intentionally planted in it."""

    model_config = ConfigDict(extra="forbid")

    events: list[Event]
    scenario: str
    seed: int
    planted_anomalies: list[dict[str, Any]] = Field(default_factory=list)


class SyntheticGenerator:
    """Generate a mixed event stream from the YAML scenario profiles.

    ``count`` means the number of telemetry packets. Each packet is paired with
    one scenario-specific environment, satellite, or cyber event when that
    profile defines one.
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        bundle = load_config(Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR)
        scenario_config = bundle.get("scenarios", {})
        profiles = scenario_config.get("scenarios", {})
        if set(profiles) != set(SCENARIOS):
            raise ValueError("scenarios.yaml must define exactly the four supported scenarios")
        self.defaults: dict[str, Any] = scenario_config.get("defaults", {})
        self.profiles: dict[str, dict[str, Any]] = profiles

    def generate(
        self,
        scenario: str,
        count: int | None = None,
        seed: int = 0,
        plant_anomalies: list[str] | None = None,
        noise: float | None = None,
        drift: float | None = None,
    ) -> SyntheticResult:
        """Generate one deterministic scenario run.

        ``plant_anomalies=["all"]`` plants one instance of each supported
        telemetry fault. An explicit list plants only the requested faults.
        """
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; expected {list(SCENARIOS)}")

        total = int(count if count is not None else self.defaults.get("count", 24))
        if total < 1:
            raise ValueError("count must be positive")

        requested = self._requested_anomalies(plant_anomalies)
        if len(requested) > total:
            raise ValueError("count must be at least the number of requested anomaly types")

        noise_value = float(self.defaults.get("noise", 0.02) if noise is None else noise)
        drift_value = float(self.defaults.get("drift", 0.01) if drift is None else drift)
        self._validate_number("noise", noise_value, minimum=0)
        self._validate_number("drift", drift_value)

        profile = self.profiles[scenario]
        interval = float(self.defaults.get("interval_seconds", 60))
        self._validate_number("interval_seconds", interval, minimum=0.001)
        start = self._start_time()
        location = GeoPoint(**profile.get("location", self.defaults["location"]))
        rng = random.Random(seed)
        positions = self._fault_positions(total, requested)
        events: list[Event] = []
        planted: list[dict[str, Any]] = []

        for index in range(total):
            received_at = start + timedelta(seconds=interval * index + 1)
            timestamp = start + timedelta(seconds=interval * index)
            payload = self._telemetry_payload(profile, index, rng, noise_value, drift_value)
            faults = [kind for kind, position in positions.items() if position == index]

            for fault in faults:
                timestamp = self._apply_fault(fault, payload, timestamp, index)

            payload["timestamp"] = timestamp.isoformat()
            payload["faults"] = faults
            event_id = f"evt_{scenario}_{seed}_{index:06d}_telemetry"
            telemetry_event = self._event(
                event_id=event_id,
                source_id=str(profile["source_id"]),
                event_type="telemetry",
                timestamp=timestamp,
                received_at=received_at,
                location=location,
                payload=payload,
                scenario=scenario,
                stream_index=index,
                planted_faults=faults,
            )
            events.append(telemetry_event)

            for event_type in ("environment", "satellite", "cyber"):
                if event_type not in profile:
                    continue
                side_payload = dict(profile[event_type])
                side_payload.update({"scenario": scenario, "stream_index": index})
                side_event = self._event(
                    event_id=f"evt_{scenario}_{seed}_{index:06d}_{event_type}",
                    source_id=f"{profile['source_id']}-{event_type}",
                    event_type=event_type,
                    timestamp=start + timedelta(seconds=interval * index),
                    received_at=received_at,
                    location=location,
                    payload=side_payload,
                    scenario=scenario,
                    stream_index=index,
                    planted_faults=[],
                )
                events.append(side_event)

            for fault in faults:
                planted.append(
                    {
                        "event_id": event_id,
                        "event_index": index,
                        "type": fault,
                    }
                )

        return SyntheticResult(
            events=events,
            scenario=scenario,
            seed=seed,
            planted_anomalies=planted,
        )

    def _requested_anomalies(self, requested: list[str] | None) -> list[str]:
        if requested == ["all"]:
            return list(ANOMALIES)
        selected = list(requested or [])
        unknown = set(selected).difference(ANOMALIES)
        if unknown:
            raise ValueError(f"unknown anomaly type(s): {sorted(unknown)}")
        if len(set(selected)) != len(selected):
            raise ValueError("anomaly types must not be repeated")
        return selected

    @staticmethod
    def _fault_positions(total: int, faults: list[str]) -> dict[str, int]:
        if not faults:
            return {}
        return {
            fault: (index * total) // len(faults)
            for index, fault in enumerate(faults)
        }

    def _telemetry_payload(
        self,
        profile: dict[str, Any],
        index: int,
        rng: random.Random,
        noise: float,
        drift: float,
    ) -> dict[str, Any]:
        base = profile.get("telemetry", {})
        if not isinstance(base, dict):
            raise ValueError("scenario telemetry profile must be a mapping")
        payload: dict[str, Any] = {}
        for name, value in base.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                payload[name] = value
                continue
            scale = max(abs(float(value)), 1.0)
            payload[name] = float(value) + rng.uniform(-noise, noise) * scale + drift * index
        payload.update(
            {
                "seq": index,
                "session_id": f"{profile['source_id']}-session",
                "lat": profile.get("location", self.defaults["location"])["lat"],
                "lon": profile.get("location", self.defaults["location"])["lon"],
            }
        )
        return payload

    def _apply_fault(
        self,
        fault: str,
        payload: dict[str, Any],
        timestamp: datetime,
        index: int,
    ) -> datetime:
        fault_config = self.defaults.get("faults", {}).get(fault, {})
        if fault == "missing_field":
            payload.pop(str(fault_config["field"]), None)
        elif fault == "out_of_range":
            payload[str(fault_config["field"])] = fault_config["value"]
        elif fault == "wrong_type":
            payload[str(fault_config["field"])] = fault_config["value"]
        elif fault == "duplicate_sequence":
            payload["seq"] = max(0, index + int(fault_config["offset"]))
        elif fault == "gap_out_of_order":
            payload["seq"] = index + int(fault_config["seq_jump"])
            timestamp += timedelta(seconds=float(fault_config["timestamp_offset_seconds"]))
        elif fault == "stale_data":
            timestamp -= timedelta(seconds=float(fault_config["age_seconds"]))
        elif fault == "sudden_jump":
            field = str(fault_config["field"])
            payload[field] = float(payload[field]) + float(fault_config["delta"])
        return timestamp

    def _start_time(self) -> datetime:
        raw = str(self.defaults.get("start_time", "2026-01-01T00:00:00Z"))
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("scenarios.defaults.start_time must include a timezone")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _validate_number(name: str, value: float, minimum: float | None = None) -> None:
        if not math.isfinite(value) or minimum is not None and value < minimum:
            suffix = f" >= {minimum}" if minimum is not None else ""
            raise ValueError(f"{name} must be finite{suffix}")

    @staticmethod
    def _event(
        event_id: str,
        source_id: str,
        event_type: str,
        timestamp: datetime,
        received_at: datetime,
        location: GeoPoint,
        payload: dict[str, Any],
        scenario: str,
        stream_index: int,
        planted_faults: list[str],
    ) -> Event:
        return Event(
            id=event_id,
            source_id=source_id,
            type=event_type,
            timestamp=timestamp,
            received_at=received_at,
            geo=location,
            payload=payload,
            raw_ref=f"synthetic://{event_id}",
            metadata={
                "synthetic": True,
                "scenario": scenario,
                "stream_index": stream_index,
                "planted_faults": planted_faults,
            },
        )
